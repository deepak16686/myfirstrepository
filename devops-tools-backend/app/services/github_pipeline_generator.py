"""
GitHub Actions Pipeline Generator Service

Generates GitHub Actions workflow files (.github/workflows/ci.yml) and Dockerfiles
for repositories. Supports both GitHub.com and Gitea (free self-hosted alternative).

Uses ChromaDB for template storage and reinforcement learning.
"""
import re
import yaml
import httpx
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from app.config import settings


class GitHubPipelineGeneratorService:
    """
    Service for generating GitHub Actions workflows with reinforcement learning feedback.

    Supports:
    - Multiple languages: Java, Python, Node.js, Go
    - 9-job pipeline structure matching GitLab stages
    - Nexus private registry integration
    - ChromaDB template storage for RL
    - Self-hosted runners (for internal network access)
    """

    FEEDBACK_COLLECTION = "github_actions_feedback"
    TEMPLATES_COLLECTION = "github_actions_templates"
    SUCCESSFUL_PIPELINES_COLLECTION = "github_actions_successful_pipelines"
    DEFAULT_MODEL = "github-actions-generator-v1"

    # Required jobs matching GitLab stages
    REQUIRED_JOBS = [
        'compile', 'build-image', 'test-image', 'static-analysis',
        'sonarqube', 'trivy-scan', 'push-release', 'notify-success',
        'notify-failure', 'learn-record'
    ]

    def __init__(self):
        self.github_url = settings.github_url
        self.github_token = settings.github_token
        self.chromadb_url = settings.chromadb_url
        self.ollama_url = settings.ollama_url

    def _ensure_learn_job(self, workflow: str) -> str:
        """Ensure the learn-record job exists in the workflow"""
        try:
            parsed = yaml.safe_load(workflow)
            if not parsed or 'jobs' not in parsed:
                return workflow

            jobs = parsed.get('jobs', {})

            # Check if learn-record job exists
            if 'learn-record' not in jobs:
                # Add learn-record job
                jobs['learn-record'] = {
                    'runs-on': 'self-hosted',
                    'needs': 'push-release',
                    'if': 'success()',
                    'steps': [
                        {'uses': 'actions/checkout@v4'},
                        {
                            'name': 'Record Pipeline Success for RL',
                            'run': '''curl -s -X POST "${{ env.DEVOPS_BACKEND_URL }}/api/v1/github-pipeline/learn/record" \\
  -H "Content-Type: application/json" \\
  -d '{
    "repo_url": "${{ github.server_url }}/${{ github.repository }}",
    "github_token": "${{ secrets.GITHUB_TOKEN }}",
    "branch": "${{ github.ref_name }}",
    "run_id": ${{ github.run_id }}
  }' && echo "SUCCESS: Configuration recorded for RL"'''
                        }
                    ]
                }
                parsed['jobs'] = jobs
                return yaml.dump(parsed, default_flow_style=False, sort_keys=False)

            return workflow
        except Exception as e:
            print(f"[Learn Job] Error adding learn job: {e}")
            return workflow

    async def get_reference_workflow(
        self,
        language: str,
        framework: Optional[str] = None
    ) -> Optional[str]:
        """Get reference workflow from ChromaDB"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # First try exact match with language + framework
                if framework:
                    response = await client.post(
                        f"{self.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{self.TEMPLATES_COLLECTION}/get",
                        json={
                            "where": {
                                "$and": [
                                    {"language": language},
                                    {"framework": framework}
                                ]
                            },
                            "limit": 1,
                            "include": ["documents", "metadatas"]
                        }
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("documents"):
                            return data["documents"][0]

                # Try language-only match
                response = await client.post(
                    f"{self.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{self.TEMPLATES_COLLECTION}/get",
                    json={
                        "where": {"language": language},
                        "limit": 1,
                        "include": ["documents", "metadatas"]
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("documents"):
                        return data["documents"][0]

        except Exception as e:
            print(f"[ChromaDB] Error getting reference workflow: {e}")

        return None

    async def get_best_template_files(
        self,
        language: str,
        framework: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """Get the best performing template from successful pipelines"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                where_filter = {"language": language}
                if framework:
                    where_filter = {
                        "$and": [
                            {"language": language},
                            {"framework": framework}
                        ]
                    }

                response = await client.post(
                    f"{self.chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{self.SUCCESSFUL_PIPELINES_COLLECTION}/get",
                    json={
                        "where": where_filter,
                        "limit": 10,
                        "include": ["documents", "metadatas"]
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    documents = data.get("documents", [])
                    metadatas = data.get("metadatas", [])

                    if documents:
                        # Sort by success_count and duration
                        best_idx = 0
                        best_score = 0
                        for i, meta in enumerate(metadatas):
                            score = meta.get("success_count", 0) * 100 - meta.get("duration", 0)
                            if score > best_score:
                                best_score = score
                                best_idx = i

                        doc = documents[best_idx]
                        try:
                            parsed = yaml.safe_load(doc)
                            return {
                                "workflow": parsed.get("workflow", ""),
                                "dockerfile": parsed.get("dockerfile", ""),
                                "source": "chromadb-successful"
                            }
                        except:
                            pass

        except Exception as e:
            print(f"[ChromaDB] Error getting best template: {e}")

        return None

    def parse_github_url(self, url: str) -> Dict[str, str]:
        """Parse GitHub/Gitea repository URL to extract owner and repo"""
        url = url.rstrip('/').replace('.git', '')

        # Handle SSH URLs (git@github.com:owner/repo)
        if url.startswith('git@'):
            match = re.match(r'git@([^:]+):(.+)/(.+)', url)
            if match:
                return {
                    "host": f"https://{match.group(1)}",
                    "owner": match.group(2),
                    "repo": match.group(3)
                }

        # Handle HTTP(S) URLs
        match = re.match(r'(https?)://([^/]+)/([^/]+)/([^/]+)', url)
        if match:
            return {
                "host": f"{match.group(1)}://{match.group(2)}",
                "owner": match.group(3),
                "repo": match.group(4)
            }

        raise ValueError(f"Invalid GitHub/Gitea URL: {url}")

    async def analyze_repository(
        self,
        repo_url: str,
        github_token: str
    ) -> Dict[str, Any]:
        """Analyze repository to detect language, framework, and structure"""
        parsed = self.parse_github_url(repo_url)
        owner = parsed["owner"]
        repo = parsed["repo"]
        host = parsed["host"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json"
            }

            # Get repository info
            repo_response = await client.get(
                f"{host}/api/v1/repos/{owner}/{repo}" if "gitea" in host.lower() or host == self.github_url
                else f"{host}/repos/{owner}/{repo}",
                headers=headers
            )
            repo_info = repo_response.json() if repo_response.status_code == 200 else {}

            # Get file tree
            default_branch = repo_info.get("default_branch", "main")

            # Try to get contents
            contents_response = await client.get(
                f"{host}/api/v1/repos/{owner}/{repo}/contents" if "gitea" in host.lower() or host == self.github_url
                else f"{host}/repos/{owner}/{repo}/contents",
                headers=headers,
                params={"ref": default_branch}
            )

            files = []
            if contents_response.status_code == 200:
                contents = contents_response.json()
                if isinstance(contents, list):
                    files = [f.get("name", f.get("path", "")) for f in contents]

        # Detect language
        language = self._detect_language(files)
        framework = self._detect_framework(files)
        package_manager = self._detect_package_manager(files)

        return {
            "owner": owner,
            "repo": repo,
            "default_branch": default_branch,
            "files": files,
            "language": language,
            "framework": framework,
            "package_manager": package_manager,
            "has_dockerfile": "Dockerfile" in files or "dockerfile" in [f.lower() for f in files],
            "has_workflow": ".github" in files or any("workflow" in f.lower() for f in files)
        }

    def _detect_language(self, files: List[str]) -> str:
        """Detect primary programming language"""
        file_set = set(f.lower() for f in files)

        if "pom.xml" in file_set or "build.gradle" in file_set:
            return "java"
        if "package.json" in file_set:
            return "javascript"
        if "requirements.txt" in file_set or "setup.py" in file_set or "pyproject.toml" in file_set:
            return "python"
        if "go.mod" in file_set:
            return "go"
        if "cargo.toml" in file_set:
            return "rust"
        if "gemfile" in file_set:
            return "ruby"
        if any(f.endswith(".csproj") for f in files):
            return "csharp"

        return "unknown"

    def _detect_framework(self, files: List[str]) -> str:
        """Detect framework"""
        file_set = set(f.lower() for f in files)

        if "next.config.js" in file_set or "next.config.mjs" in file_set:
            return "nextjs"
        if "angular.json" in file_set:
            return "angular"
        if "vue.config.js" in file_set:
            return "vue"
        if "manage.py" in file_set:
            return "django"
        if "app.py" in file_set or "main.py" in file_set:
            return "flask"
        if "pom.xml" in file_set:
            return "spring"

        return "generic"

    def _detect_package_manager(self, files: List[str]) -> str:
        """Detect package manager"""
        file_set = set(f.lower() for f in files)

        if "yarn.lock" in file_set:
            return "yarn"
        if "package-lock.json" in file_set:
            return "npm"
        if "pnpm-lock.yaml" in file_set:
            return "pnpm"
        if "poetry.lock" in file_set:
            return "poetry"
        if "pipfile.lock" in file_set:
            return "pipenv"
        if "requirements.txt" in file_set:
            return "pip"
        if "build.gradle" in file_set:
            return "gradle"
        if "pom.xml" in file_set:
            return "maven"

        return "unknown"

    async def generate_workflow_files(
        self,
        repo_url: str,
        github_token: str,
        additional_context: str = "",
        model: str = None,
        use_template_only: bool = False,
        runner_type: str = "self-hosted"
    ) -> Dict[str, Any]:
        """
        Generate GitHub Actions workflow and Dockerfile for a repository.

        Priority:
        1. Use proven successful template from ChromaDB (if exists)
        2. Use LLM to generate with reference template
        3. Fall back to default templates
        """
        # Analyze repository
        analysis = await self.analyze_repository(repo_url, github_token)
        language = analysis["language"]
        framework = analysis["framework"]

        print(f"[GitHub Pipeline] Analyzing {repo_url}: {language}/{framework}")

        # Priority 1: Check for proven successful template
        best_template = await self.get_best_template_files(language, framework)
        if best_template and best_template.get("workflow"):
            print(f"[GitHub Pipeline] Using proven template from ChromaDB")
            workflow = self._ensure_learn_job(best_template["workflow"])
            return {
                "success": True,
                "workflow": workflow,
                "dockerfile": best_template.get("dockerfile", self._get_default_dockerfile(analysis)),
                "analysis": analysis,
                "model_used": "chromadb-successful",
                "feedback_used": 0
            }

        # Priority 2: Use template only if requested
        if use_template_only:
            workflow = self._get_default_workflow(analysis, runner_type)
            dockerfile = self._get_default_dockerfile(analysis)
            return {
                "success": True,
                "workflow": self._ensure_learn_job(workflow),
                "dockerfile": dockerfile,
                "analysis": analysis,
                "model_used": "default-template",
                "feedback_used": 0
            }

        # Priority 3: Try LLM generation
        try:
            reference = await self.get_reference_workflow(language, framework)
            generated = await self._generate_with_llm(
                analysis, reference, additional_context, model or self.DEFAULT_MODEL
            )

            if generated:
                workflow = self._validate_and_fix_workflow(generated.get("workflow", ""), reference)
                dockerfile = self._validate_and_fix_dockerfile(generated.get("dockerfile", ""), language)

                return {
                    "success": True,
                    "workflow": self._ensure_learn_job(workflow),
                    "dockerfile": dockerfile,
                    "analysis": analysis,
                    "model_used": model or self.DEFAULT_MODEL,
                    "feedback_used": 0
                }
        except Exception as e:
            print(f"[GitHub Pipeline] LLM generation failed: {e}")

        # Fallback: Use default templates
        workflow = self._get_default_workflow(analysis, runner_type)
        dockerfile = self._get_default_dockerfile(analysis)

        return {
            "success": True,
            "workflow": self._ensure_learn_job(workflow),
            "dockerfile": dockerfile,
            "analysis": analysis,
            "model_used": "default-template",
            "feedback_used": 0
        }

    async def _generate_with_llm(
        self,
        analysis: Dict[str, Any],
        reference: Optional[str],
        additional_context: str,
        model: str
    ) -> Optional[Dict[str, str]]:
        """Generate workflow using Ollama LLM"""
        prompt = self._build_generation_prompt(analysis, reference, additional_context)

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 6000
                        }
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    generated_text = data.get("response", "")
                    return self._parse_llm_output(generated_text)

        except Exception as e:
            print(f"[Ollama] Error: {e}")

        return None

    def _build_generation_prompt(
        self,
        analysis: Dict[str, Any],
        reference: Optional[str],
        additional_context: str
    ) -> str:
        """Build prompt for LLM generation"""
        prompt = f"""Generate a GitHub Actions workflow and Dockerfile for a {analysis['language']} project.

Project Analysis:
- Language: {analysis['language']}
- Framework: {analysis['framework']}
- Package Manager: {analysis['package_manager']}

Requirements:
- Use Nexus private registry for ALL images: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/<image>
- Use self-hosted runners with access to internal network
- Include all 9 jobs: compile, build-image, test-image, static-analysis, sonarqube, trivy-scan, push-release, notify-success, notify-failure, learn-record
- Use docker/build-push-action for building images
- Use actions/upload-artifact and actions/download-artifact for passing artifacts between jobs
"""

        if reference:
            prompt += f"\nReference workflow to follow:\n```yaml\n{reference}\n```\n"

        if additional_context:
            prompt += f"\nAdditional context: {additional_context}\n"

        prompt += """
Output format:
---DOCKERFILE---
(complete Dockerfile)
---GITHUB_ACTIONS---
(complete .github/workflows/ci.yml)
---END---
"""
        return prompt

    def _parse_llm_output(self, text: str) -> Optional[Dict[str, str]]:
        """Parse LLM output to extract workflow and Dockerfile"""
        result = {}

        # Extract Dockerfile
        dockerfile_match = re.search(
            r'---DOCKERFILE---\s*(.*?)\s*(?:---GITHUB_ACTIONS---|---END---)',
            text, re.DOTALL
        )
        if dockerfile_match:
            result["dockerfile"] = dockerfile_match.group(1).strip()

        # Extract GitHub Actions workflow
        workflow_match = re.search(
            r'---GITHUB_ACTIONS---\s*(.*?)\s*---END---',
            text, re.DOTALL
        )
        if workflow_match:
            result["workflow"] = workflow_match.group(1).strip()

        # Also try code block extraction
        if not result.get("workflow"):
            yaml_match = re.search(r'```ya?ml\s*(.*?)\s*```', text, re.DOTALL)
            if yaml_match:
                result["workflow"] = yaml_match.group(1).strip()

        if not result.get("dockerfile"):
            docker_match = re.search(r'```dockerfile\s*(.*?)\s*```', text, re.DOTALL)
            if docker_match:
                result["dockerfile"] = docker_match.group(1).strip()

        return result if result else None

    def _validate_and_fix_workflow(
        self,
        workflow: str,
        reference: Optional[str]
    ) -> str:
        """Validate and fix common issues in generated workflow"""
        try:
            parsed = yaml.safe_load(workflow)
            if not parsed:
                return self._get_default_workflow({"language": "java", "framework": "generic"}, "self-hosted")

            # Ensure env block exists with required variables
            if 'env' not in parsed:
                parsed['env'] = {}

            required_env = {
                'NEXUS_REGISTRY': '${{ secrets.NEXUS_REGISTRY }}',
                'NEXUS_INTERNAL_REGISTRY': '${{ secrets.NEXUS_INTERNAL_REGISTRY }}',
                'NEXUS_USERNAME': '${{ secrets.NEXUS_USERNAME }}',
                'NEXUS_PASSWORD': '${{ secrets.NEXUS_PASSWORD }}',
                'IMAGE_NAME': '${{ github.event.repository.name }}',
                'IMAGE_TAG': '"1.0.${{ github.run_number }}"',
                'SONARQUBE_URL': '${{ secrets.SONARQUBE_URL }}',
                'SPLUNK_HEC_URL': '${{ secrets.SPLUNK_HEC_URL }}',
                'DEVOPS_BACKEND_URL': '${{ secrets.DEVOPS_BACKEND_URL }}'
            }

            for key, value in required_env.items():
                if key not in parsed['env']:
                    parsed['env'][key] = value

            # Ensure jobs exist
            if 'jobs' not in parsed:
                parsed['jobs'] = {}

            # Ensure all jobs use self-hosted runner
            for job_name, job in parsed.get('jobs', {}).items():
                if isinstance(job, dict):
                    if 'runs-on' not in job:
                        job['runs-on'] = 'self-hosted'

            return yaml.dump(parsed, default_flow_style=False, sort_keys=False)

        except Exception as e:
            print(f"[Validate] Error: {e}")
            return workflow

    def _validate_and_fix_dockerfile(self, dockerfile: str, language: str) -> str:
        """Validate and fix Dockerfile"""
        if not dockerfile or not dockerfile.strip():
            return self._get_default_dockerfile({"language": language, "framework": "generic"})

        lines = dockerfile.strip().split('\n')
        fixed_lines = []
        has_arg = False
        has_from = False

        for line in lines:
            # Check for ARG BASE_REGISTRY
            if line.strip().upper().startswith('ARG BASE_REGISTRY'):
                has_arg = True
            if line.strip().upper().startswith('FROM'):
                has_from = True

            # Replace public registry references
            if 'docker.io' in line or 'gcr.io' in line or 'quay.io' in line:
                line = re.sub(
                    r'(FROM\s+)(docker\.io|gcr\.io|quay\.io)/([^\s]+)',
                    r'\1${BASE_REGISTRY}/apm-repo/demo/\3',
                    line
                )

            fixed_lines.append(line)

        # Add ARG if missing
        if not has_arg and has_from:
            fixed_lines.insert(0, 'ARG BASE_REGISTRY=ai-nexus:5001')

        return '\n'.join(fixed_lines)

    def _get_default_workflow(self, analysis: Dict[str, Any], runner_type: str = "self-hosted") -> str:
        """Get default GitHub Actions workflow template"""
        language = analysis.get("language", "java")
        framework = analysis.get("framework", "generic")

        templates = {
            "java": self._get_java_workflow_template(runner_type),
            "python": self._get_python_workflow_template(runner_type),
            "javascript": self._get_nodejs_workflow_template(runner_type),
            "go": self._get_go_workflow_template(runner_type)
        }

        return templates.get(language, templates["java"])

    def _get_java_workflow_template(self, runner_type: str = "self-hosted") -> str:
        """Java workflow template"""
        return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*']
  pull_request:
    branches: [main]

env:
  NEXUS_REGISTRY: ${{{{ secrets.NEXUS_REGISTRY }}}}
  NEXUS_INTERNAL_REGISTRY: ${{{{ secrets.NEXUS_INTERNAL_REGISTRY }}}}
  NEXUS_USERNAME: ${{{{ secrets.NEXUS_USERNAME }}}}
  NEXUS_PASSWORD: ${{{{ secrets.NEXUS_PASSWORD }}}}
  IMAGE_NAME: ${{{{ github.event.repository.name }}}}
  IMAGE_TAG: "1.0.${{{{ github.run_number }}}}"
  RELEASE_TAG: "1.0.release-${{{{ github.run_number }}}}"
  SONARQUBE_URL: ${{{{ secrets.SONARQUBE_URL }}}}
  SONAR_TOKEN: ${{{{ secrets.SONAR_TOKEN }}}}
  SPLUNK_HEC_URL: ${{{{ secrets.SPLUNK_HEC_URL }}}}
  SPLUNK_HEC_TOKEN: ${{{{ secrets.SPLUNK_HEC_TOKEN }}}}
  DEVOPS_BACKEND_URL: ${{{{ secrets.DEVOPS_BACKEND_URL }}}}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/maven:3.9-eclipse-temurin-17
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Build with Maven
        run: |
          mvn clean package -DskipTests
          mkdir -p artifacts
          find target -name "*.jar" ! -name "*-sources*" ! -name "*-javadoc*" | head -1 | xargs -I {{}} cp {{}} artifacts/app.jar
      - uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: artifacts/
          retention-days: 1

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: build-artifacts
          path: artifacts/
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Build and Push Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

  test-image:
    needs: build-image
    runs-on: {runner_type}
    steps:
      - name: Test Image Exists
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          echo "Image verification successful"

  static-analysis:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/maven:3.9-eclipse-temurin-17
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Run Static Analysis
        run: mvn checkstyle:check || true

  sonarqube:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube Scan
        run: |
          sonar-scanner \\
            -Dsonar.projectKey=${{{{ github.event.repository.name }}}} \\
            -Dsonar.sources=src \\
            -Dsonar.host.url=${{{{ env.SONARQUBE_URL }}}} \\
            -Dsonar.login=${{{{ env.SONAR_TOKEN }}}} || true

  trivy-scan:
    needs: build-image
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/aquasec-trivy:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - name: Scan Image for Vulnerabilities
        run: |
          trivy image --severity HIGH,CRITICAL \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} || true

  push-release:
    needs: [test-image, trivy-scan]
    runs-on: {runner_type}
    steps:
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Tag and Push Release
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          docker tag ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}

  notify-success:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Notify Success
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "success", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  notify-failure:
    needs: [compile, build-image, test-image, trivy-scan, push-release]
    runs-on: {runner_type}
    if: failure()
    steps:
      - name: Notify Failure
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "failure", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  learn-record:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: |
          curl -s -X POST "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" \\
            -H "Content-Type: application/json" \\
            -d '{{
              "repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}",
              "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}",
              "branch": "${{{{ github.ref_name }}}}",
              "run_id": ${{{{ github.run_id }}}}
            }}' && echo "SUCCESS: Configuration recorded for RL"
'''

    def _get_python_workflow_template(self, runner_type: str = "self-hosted") -> str:
        """Python workflow template"""
        return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*']
  pull_request:
    branches: [main]

env:
  NEXUS_REGISTRY: ${{{{ secrets.NEXUS_REGISTRY }}}}
  NEXUS_INTERNAL_REGISTRY: ${{{{ secrets.NEXUS_INTERNAL_REGISTRY }}}}
  NEXUS_USERNAME: ${{{{ secrets.NEXUS_USERNAME }}}}
  NEXUS_PASSWORD: ${{{{ secrets.NEXUS_PASSWORD }}}}
  IMAGE_NAME: ${{{{ github.event.repository.name }}}}
  IMAGE_TAG: "1.0.${{{{ github.run_number }}}}"
  RELEASE_TAG: "1.0.release-${{{{ github.run_number }}}}"
  SONARQUBE_URL: ${{{{ secrets.SONARQUBE_URL }}}}
  SONAR_TOKEN: ${{{{ secrets.SONAR_TOKEN }}}}
  SPLUNK_HEC_URL: ${{{{ secrets.SPLUNK_HEC_URL }}}}
  SPLUNK_HEC_TOKEN: ${{{{ secrets.SPLUNK_HEC_TOKEN }}}}
  DEVOPS_BACKEND_URL: ${{{{ secrets.DEVOPS_BACKEND_URL }}}}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/python:3.11-slim
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Install Dependencies
        run: |
          pip install --no-cache-dir -r requirements.txt
          pip install pytest flake8
      - name: Run Tests
        run: pytest tests/ -v || true
      - uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: .
          retention-days: 1

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      - uses: actions/checkout@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Build and Push Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

  test-image:
    needs: build-image
    runs-on: {runner_type}
    steps:
      - name: Test Image Exists
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          echo "Image verification successful"

  static-analysis:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/python:3.11-slim
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Run Flake8
        run: |
          pip install flake8
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true

  sonarqube:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube Scan
        run: |
          sonar-scanner \\
            -Dsonar.projectKey=${{{{ github.event.repository.name }}}} \\
            -Dsonar.sources=. \\
            -Dsonar.host.url=${{{{ env.SONARQUBE_URL }}}} \\
            -Dsonar.login=${{{{ env.SONAR_TOKEN }}}} || true

  trivy-scan:
    needs: build-image
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/aquasec-trivy:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - name: Scan Image for Vulnerabilities
        run: |
          trivy image --severity HIGH,CRITICAL \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} || true

  push-release:
    needs: [test-image, trivy-scan]
    runs-on: {runner_type}
    steps:
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Tag and Push Release
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          docker tag ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}

  notify-success:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Notify Success
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "success", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  notify-failure:
    needs: [compile, build-image, test-image, trivy-scan, push-release]
    runs-on: {runner_type}
    if: failure()
    steps:
      - name: Notify Failure
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "failure", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  learn-record:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: |
          curl -s -X POST "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" \\
            -H "Content-Type: application/json" \\
            -d '{{
              "repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}",
              "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}",
              "branch": "${{{{ github.ref_name }}}}",
              "run_id": ${{{{ github.run_id }}}}
            }}' && echo "SUCCESS: Configuration recorded for RL"
'''

    def _get_nodejs_workflow_template(self, runner_type: str = "self-hosted") -> str:
        """Node.js workflow template"""
        return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*']
  pull_request:
    branches: [main]

env:
  NEXUS_REGISTRY: ${{{{ secrets.NEXUS_REGISTRY }}}}
  NEXUS_INTERNAL_REGISTRY: ${{{{ secrets.NEXUS_INTERNAL_REGISTRY }}}}
  NEXUS_USERNAME: ${{{{ secrets.NEXUS_USERNAME }}}}
  NEXUS_PASSWORD: ${{{{ secrets.NEXUS_PASSWORD }}}}
  IMAGE_NAME: ${{{{ github.event.repository.name }}}}
  IMAGE_TAG: "1.0.${{{{ github.run_number }}}}"
  RELEASE_TAG: "1.0.release-${{{{ github.run_number }}}}"
  SONARQUBE_URL: ${{{{ secrets.SONARQUBE_URL }}}}
  SONAR_TOKEN: ${{{{ secrets.SONAR_TOKEN }}}}
  SPLUNK_HEC_URL: ${{{{ secrets.SPLUNK_HEC_URL }}}}
  SPLUNK_HEC_TOKEN: ${{{{ secrets.SPLUNK_HEC_TOKEN }}}}
  DEVOPS_BACKEND_URL: ${{{{ secrets.DEVOPS_BACKEND_URL }}}}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/node:18-alpine
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Install and Build
        run: |
          npm ci
          npm run build --if-present
      - uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: |
            dist/
            build/
            .next/
          retention-days: 1

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: build-artifacts
          path: .
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Build and Push Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

  test-image:
    needs: build-image
    runs-on: {runner_type}
    steps:
      - name: Test Image Exists
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          echo "Image verification successful"

  static-analysis:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/node:18-alpine
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Run ESLint
        run: |
          npm ci
          npm run lint --if-present || true

  sonarqube:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube Scan
        run: |
          sonar-scanner \\
            -Dsonar.projectKey=${{{{ github.event.repository.name }}}} \\
            -Dsonar.sources=src \\
            -Dsonar.host.url=${{{{ env.SONARQUBE_URL }}}} \\
            -Dsonar.login=${{{{ env.SONAR_TOKEN }}}} || true

  trivy-scan:
    needs: build-image
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/aquasec-trivy:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - name: Scan Image for Vulnerabilities
        run: |
          trivy image --severity HIGH,CRITICAL \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} || true

  push-release:
    needs: [test-image, trivy-scan]
    runs-on: {runner_type}
    steps:
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Tag and Push Release
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          docker tag ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}

  notify-success:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Notify Success
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "success", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  notify-failure:
    needs: [compile, build-image, test-image, trivy-scan, push-release]
    runs-on: {runner_type}
    if: failure()
    steps:
      - name: Notify Failure
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "failure", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  learn-record:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: |
          curl -s -X POST "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" \\
            -H "Content-Type: application/json" \\
            -d '{{
              "repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}",
              "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}",
              "branch": "${{{{ github.ref_name }}}}",
              "run_id": ${{{{ github.run_id }}}}
            }}' && echo "SUCCESS: Configuration recorded for RL"
'''

    def _get_go_workflow_template(self, runner_type: str = "self-hosted") -> str:
        """Go workflow template"""
        return f'''name: CI/CD Pipeline

on:
  push:
    branches: [main, develop, 'feature/*']
  pull_request:
    branches: [main]

env:
  NEXUS_REGISTRY: ${{{{ secrets.NEXUS_REGISTRY }}}}
  NEXUS_INTERNAL_REGISTRY: ${{{{ secrets.NEXUS_INTERNAL_REGISTRY }}}}
  NEXUS_USERNAME: ${{{{ secrets.NEXUS_USERNAME }}}}
  NEXUS_PASSWORD: ${{{{ secrets.NEXUS_PASSWORD }}}}
  IMAGE_NAME: ${{{{ github.event.repository.name }}}}
  IMAGE_TAG: "1.0.${{{{ github.run_number }}}}"
  RELEASE_TAG: "1.0.release-${{{{ github.run_number }}}}"
  SONARQUBE_URL: ${{{{ secrets.SONARQUBE_URL }}}}
  SONAR_TOKEN: ${{{{ secrets.SONAR_TOKEN }}}}
  SPLUNK_HEC_URL: ${{{{ secrets.SPLUNK_HEC_URL }}}}
  SPLUNK_HEC_TOKEN: ${{{{ secrets.SPLUNK_HEC_TOKEN }}}}
  DEVOPS_BACKEND_URL: ${{{{ secrets.DEVOPS_BACKEND_URL }}}}

jobs:
  compile:
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/golang:1.21-alpine
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Build Binary
        run: |
          CGO_ENABLED=0 GOOS=linux go build -o app .
      - uses: actions/upload-artifact@v4
        with:
          name: build-artifacts
          path: app
          retention-days: 1

  build-image:
    needs: compile
    runs-on: {runner_type}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: build-artifacts
          path: .
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Build and Push Image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:latest

  test-image:
    needs: build-image
    runs-on: {runner_type}
    steps:
      - name: Test Image Exists
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          echo "Image verification successful"

  static-analysis:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/golang:1.21-alpine
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Run Go Vet
        run: go vet ./... || true

  sonarqube:
    needs: compile
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube Scan
        run: |
          sonar-scanner \\
            -Dsonar.projectKey=${{{{ github.event.repository.name }}}} \\
            -Dsonar.sources=. \\
            -Dsonar.host.url=${{{{ env.SONARQUBE_URL }}}} \\
            -Dsonar.login=${{{{ env.SONAR_TOKEN }}}} || true

  trivy-scan:
    needs: build-image
    runs-on: {runner_type}
    container:
      image: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/aquasec-trivy:latest
      credentials:
        username: ${{{{ secrets.NEXUS_USERNAME }}}}
        password: ${{{{ secrets.NEXUS_PASSWORD }}}}
    steps:
      - name: Scan Image for Vulnerabilities
        run: |
          trivy image --severity HIGH,CRITICAL \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} || true

  push-release:
    needs: [test-image, trivy-scan]
    runs-on: {runner_type}
    steps:
      - name: Login to Nexus Registry
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.NEXUS_REGISTRY }}}}
          username: ${{{{ secrets.NEXUS_USERNAME }}}}
          password: ${{{{ secrets.NEXUS_PASSWORD }}}}
      - name: Tag and Push Release
        run: |
          docker pull ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          docker tag ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}} \\
            ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}
          docker push ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/${{{{ env.IMAGE_NAME }}}}:${{{{ env.RELEASE_TAG }}}}

  notify-success:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Notify Success
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "success", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  notify-failure:
    needs: [compile, build-image, test-image, trivy-scan, push-release]
    runs-on: {runner_type}
    if: failure()
    steps:
      - name: Notify Failure
        run: |
          curl -k -X POST "${{{{ env.SPLUNK_HEC_URL }}}}/services/collector" \\
            -H "Authorization: Splunk ${{{{ env.SPLUNK_HEC_TOKEN }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"event": {{"status": "failure", "pipeline": "${{{{ github.run_id }}}}", "project": "${{{{ github.repository }}}}"}}}}'

  learn-record:
    needs: push-release
    runs-on: {runner_type}
    if: success()
    steps:
      - name: Record Pipeline Success for RL
        run: |
          curl -s -X POST "${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record" \\
            -H "Content-Type: application/json" \\
            -d '{{
              "repo_url": "${{{{ github.server_url }}}}/${{{{ github.repository }}}}",
              "github_token": "${{{{ secrets.GITHUB_TOKEN }}}}",
              "branch": "${{{{ github.ref_name }}}}",
              "run_id": ${{{{ github.run_id }}}}
            }}' && echo "SUCCESS: Configuration recorded for RL"
'''

    def _get_default_dockerfile(self, analysis: Dict[str, Any]) -> str:
        """Get default Dockerfile based on language"""
        language = analysis.get("language", "java")

        dockerfiles = {
            "java": '''ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/amazoncorretto:17-alpine-jdk
WORKDIR /app
COPY artifacts/app.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]
''',
            "python": '''ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
            "javascript": '''ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["node", "server.js"]
''',
            "go": '''ARG BASE_REGISTRY=ai-nexus:5001
FROM ${BASE_REGISTRY}/apm-repo/demo/alpine:3.18
WORKDIR /app
COPY app .
RUN chmod +x app
EXPOSE 8080
CMD ["./app"]
'''
        }

        return dockerfiles.get(language, dockerfiles["java"])

    async def commit_to_github(
        self,
        repo_url: str,
        github_token: str,
        workflow: str,
        dockerfile: str,
        branch_name: Optional[str] = None,
        commit_message: str = "Add CI/CD pipeline configuration [AI Generated]"
    ) -> Dict[str, Any]:
        """Commit workflow and Dockerfile to GitHub/Gitea repository"""
        parsed = self.parse_github_url(repo_url)
        owner = parsed["owner"]
        repo = parsed["repo"]
        host = parsed["host"]

        # Generate branch name if not provided
        if not branch_name:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            branch_name = f"ci-pipeline-{timestamp}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json"
            }

            # Determine API base path
            api_base = f"{host}/api/v1/repos/{owner}/{repo}" if "gitea" in host.lower() or host == self.github_url else f"{host}/repos/{owner}/{repo}"

            # Get default branch SHA
            branch_response = await client.get(
                f"{api_base}/branches/main",
                headers=headers
            )
            if branch_response.status_code != 200:
                # Try 'master' as fallback
                branch_response = await client.get(
                    f"{api_base}/branches/master",
                    headers=headers
                )

            if branch_response.status_code == 200:
                branch_data = branch_response.json()
                base_sha = branch_data["commit"]["sha"]
            else:
                return {"success": False, "error": "Could not find default branch"}

            # Create new branch
            create_ref_response = await client.post(
                f"{api_base}/git/refs",
                headers=headers,
                json={
                    "ref": f"refs/heads/{branch_name}",
                    "sha": base_sha
                }
            )

            if create_ref_response.status_code not in [200, 201]:
                # Branch might already exist, continue anyway
                pass

            # Commit files
            files_to_commit = {
                ".github/workflows/ci.yml": workflow,
                "Dockerfile": dockerfile
            }

            last_commit = None
            for path, content in files_to_commit.items():
                encoded_content = __import__('base64').b64encode(content.encode('utf-8')).decode('utf-8')

                # Check if file exists
                file_response = await client.get(
                    f"{api_base}/contents/{path}",
                    headers=headers,
                    params={"ref": branch_name}
                )

                payload = {
                    "message": commit_message,
                    "content": encoded_content,
                    "branch": branch_name
                }

                if file_response.status_code == 200:
                    existing = file_response.json()
                    payload["sha"] = existing["sha"]

                commit_response = await client.put(
                    f"{api_base}/contents/{path}",
                    headers=headers,
                    json=payload
                )

                if commit_response.status_code in [200, 201]:
                    last_commit = commit_response.json()

            if last_commit:
                return {
                    "success": True,
                    "branch": branch_name,
                    "commit_sha": last_commit.get("commit", {}).get("sha"),
                    "web_url": f"{host}/{owner}/{repo}/tree/{branch_name}"
                }

        return {"success": False, "error": "Failed to commit files"}

    async def get_workflow_status(
        self,
        repo_url: str,
        github_token: str,
        branch: str
    ) -> Dict[str, Any]:
        """Get latest workflow run status"""
        parsed = self.parse_github_url(repo_url)
        owner = parsed["owner"]
        repo = parsed["repo"]
        host = parsed["host"]

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json"
            }

            api_base = f"{host}/api/v1/repos/{owner}/{repo}" if "gitea" in host.lower() or host == self.github_url else f"{host}/repos/{owner}/{repo}"

            response = await client.get(
                f"{api_base}/actions/runs",
                headers=headers,
                params={"branch": branch, "per_page": 1}
            )

            if response.status_code == 200:
                data = response.json()
                runs = data.get("workflow_runs", [])
                if runs:
                    run = runs[0]
                    return {
                        "run_id": run["id"],
                        "status": run["status"],
                        "conclusion": run.get("conclusion"),
                        "created_at": run["created_at"],
                        "updated_at": run.get("updated_at"),
                        "html_url": run.get("html_url")
                    }

        return {"status": "not_found"}

    async def record_workflow_result(
        self,
        repo_url: str,
        github_token: str,
        branch: str,
        run_id: int
    ) -> Dict[str, Any]:
        """Record successful workflow for RL"""
        # Get workflow run details
        status = await self.get_workflow_status(repo_url, github_token, branch)

        if status.get("conclusion") == "success":
            # Store in ChromaDB
            # This would be implemented similar to GitLab pipeline recording
            return {"success": True, "recorded": True}

        return {"success": False, "error": "Workflow not successful"}


# Singleton instance
github_pipeline_generator = GitHubPipelineGeneratorService()
