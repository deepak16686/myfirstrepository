"""
GitLab Pipeline Generator Service

This service handles:
1. Generating gitlab-ci.yml and Dockerfile using Ollama
2. Committing files to GitLab repositories
3. Monitoring pipeline status
4. Storing and retrieving feedback from ChromaDB for reinforcement learning
"""
import re
import json
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import httpx

from app.config import settings, tools_manager
from app.integrations.ollama import OllamaIntegration
from app.integrations.chromadb import ChromaDBIntegration


class PipelineGeneratorService:
    """Service for generating and managing GitLab pipelines with RL feedback"""

    FEEDBACK_COLLECTION = "pipeline_feedback"

    def __init__(self):
        self.ollama_config = tools_manager.get_tool("ollama")
        self.chromadb_config = tools_manager.get_tool("chromadb")
        self.gitlab_base_url = settings.gitlab_url
        self.gitlab_token = settings.gitlab_token

    def _get_ollama(self) -> OllamaIntegration:
        return OllamaIntegration(self.ollama_config)

    def _get_chromadb(self) -> ChromaDBIntegration:
        return ChromaDBIntegration(self.chromadb_config)

    def parse_gitlab_url(self, url: str) -> Dict[str, str]:
        """
        Parse GitLab repository URL to extract project info.

        Supports:
        - https://gitlab.com/user/repo
        - https://gitlab.com/user/repo.git
        - http://localhost:8929/user/repo
        - git@gitlab.com:user/repo.git
        """
        # Remove .git suffix if present
        url = url.rstrip('/').replace('.git', '')

        # Handle SSH URLs
        if url.startswith('git@'):
            match = re.match(r'git@([^:]+):(.+)', url)
            if match:
                host = match.group(1)
                path = match.group(2)
                return {
                    "host": f"https://{host}",
                    "path": path,
                    "project_path": path.replace('/', '%2F')
                }

        # Handle HTTP(S) URLs
        match = re.match(r'https?://([^/]+)/(.+)', url)
        if match:
            host = match.group(1)
            path = match.group(2)
            return {
                "host": f"http://{host}" if 'localhost' in host else f"https://{host}",
                "path": path,
                "project_path": path.replace('/', '%2F')
            }

        raise ValueError(f"Invalid GitLab URL: {url}")

    async def analyze_repository(self, repo_url: str, gitlab_token: str) -> Dict[str, Any]:
        """
        Analyze a GitLab repository to understand its structure.
        Returns information about:
        - Programming language
        - Framework
        - Existing files
        - Package manager
        """
        parsed = self.parse_gitlab_url(repo_url)

        async with httpx.AsyncClient() as client:
            headers = {"PRIVATE-TOKEN": gitlab_token}

            # Get project info
            project_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}"
            project_resp = await client.get(project_url, headers=headers)
            project_resp.raise_for_status()
            project = project_resp.json()

            # Get repository tree (root level files)
            tree_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/tree"
            tree_resp = await client.get(tree_url, headers=headers, params={"per_page": 100})
            files = tree_resp.json() if tree_resp.status_code == 200 else []

            # Detect language and framework based on files
            file_names = [f['name'] for f in files if f['type'] == 'blob']

            analysis = {
                "project_id": project['id'],
                "project_name": project['name'],
                "default_branch": project.get('default_branch', 'main'),
                "files": file_names,
                "language": self._detect_language(file_names),
                "framework": self._detect_framework(file_names),
                "package_manager": self._detect_package_manager(file_names),
                "has_dockerfile": 'Dockerfile' in file_names,
                "has_gitlab_ci": '.gitlab-ci.yml' in file_names
            }

            return analysis

    def _detect_language(self, files: List[str]) -> str:
        """Detect primary programming language"""
        if 'package.json' in files:
            return 'javascript'
        elif 'requirements.txt' in files or 'setup.py' in files or 'pyproject.toml' in files:
            return 'python'
        elif 'pom.xml' in files or 'build.gradle' in files:
            return 'java'
        elif 'go.mod' in files:
            return 'go'
        elif 'Cargo.toml' in files:
            return 'rust'
        elif 'Gemfile' in files:
            return 'ruby'
        elif any(f.endswith('.csproj') for f in files):
            return 'csharp'
        return 'unknown'

    def _detect_framework(self, files: List[str]) -> str:
        """Detect framework based on files"""
        if 'next.config.js' in files or 'next.config.mjs' in files:
            return 'nextjs'
        elif 'angular.json' in files:
            return 'angular'
        elif 'vue.config.js' in files:
            return 'vue'
        elif 'manage.py' in files:
            return 'django'
        elif 'app.py' in files or 'main.py' in files:
            if 'requirements.txt' in files:
                return 'flask-or-fastapi'
        elif 'pom.xml' in files:
            return 'spring'
        return 'generic'

    def _detect_package_manager(self, files: List[str]) -> str:
        """Detect package manager"""
        if 'yarn.lock' in files:
            return 'yarn'
        elif 'package-lock.json' in files:
            return 'npm'
        elif 'pnpm-lock.yaml' in files:
            return 'pnpm'
        elif 'Pipfile.lock' in files:
            return 'pipenv'
        elif 'poetry.lock' in files:
            return 'poetry'
        elif 'requirements.txt' in files:
            return 'pip'
        return 'unknown'

    async def get_relevant_feedback(self, language: str, framework: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant feedback from ChromaDB based on language and framework.
        This implements the reinforcement learning aspect.
        """
        try:
            chromadb = self._get_chromadb()

            # Check if collection exists
            collection = await chromadb.get_collection(self.FEEDBACK_COLLECTION)
            if not collection:
                await chromadb.close()
                return []

            # Query for similar cases
            query_text = f"pipeline for {language} {framework} application"
            results = await chromadb.query(
                collection_id=self.FEEDBACK_COLLECTION,
                query_texts=[query_text],
                n_results=limit,
                include=["documents", "metadatas"]
            )

            await chromadb.close()

            feedback_list = []
            if results and results.get('documents'):
                for i, doc in enumerate(results['documents'][0]):
                    metadata = results['metadatas'][0][i] if results.get('metadatas') else {}
                    feedback_list.append({
                        "feedback": doc,
                        "language": metadata.get('language'),
                        "framework": metadata.get('framework'),
                        "error_type": metadata.get('error_type'),
                        "fix_description": metadata.get('fix_description')
                    })

            return feedback_list
        except Exception as e:
            print(f"Error getting feedback: {e}")
            return []

    async def generate_pipeline_files(
        self,
        repo_url: str,
        gitlab_token: str,
        additional_context: str = "",
        model: str = "qwen2.5-coder:32b-instruct-q4_K_M"
    ) -> Dict[str, str]:
        """
        Generate .gitlab-ci.yml and Dockerfile using Ollama with RL feedback.
        """
        # Analyze repository
        analysis = await self.analyze_repository(repo_url, gitlab_token)

        # Get relevant feedback from previous corrections
        feedback = await self.get_relevant_feedback(
            analysis['language'],
            analysis['framework']
        )

        # Build feedback context
        feedback_context = ""
        if feedback:
            feedback_context = "\n\n## IMPORTANT: Learn from these previous corrections:\n"
            for i, fb in enumerate(feedback, 1):
                feedback_context += f"""
### Correction {i}:
- Error Type: {fb.get('error_type', 'N/A')}
- Fix Applied: {fb.get('fix_description', 'N/A')}
- Details: {fb.get('feedback', 'N/A')}
"""

        # Generate prompt
        prompt = f"""You are an expert DevOps engineer. Generate a production-ready .gitlab-ci.yml and Dockerfile for the following project.

## Project Analysis:
- Language: {analysis['language']}
- Framework: {analysis['framework']}
- Package Manager: {analysis['package_manager']}
- Existing Files: {', '.join(analysis['files'][:20])}
- Has Dockerfile: {analysis['has_dockerfile']}
- Has GitLab CI: {analysis['has_gitlab_ci']}
{feedback_context}

## Additional Requirements:
{additional_context if additional_context else "Standard CI/CD pipeline with build, test, security scan, and deploy stages."}

## Instructions:
1. Generate a complete .gitlab-ci.yml with these stages:
   - build: Build the application/image
   - test: Run unit tests
   - security: Run security scans (use trivy for container scanning)
   - deploy: Deploy to staging/production

2. Generate a Dockerfile optimized for the detected language/framework

3. Use multi-stage builds where appropriate

4. Include proper caching strategies

5. Use GitLab CI variables for sensitive data (never hardcode secrets)

## Output Format:
Return ONLY valid YAML and Dockerfile content in this exact format:

```gitlab-ci
# Your .gitlab-ci.yml content here
```

```dockerfile
# Your Dockerfile content here
```
"""

        # Call Ollama to generate
        ollama = self._get_ollama()
        try:
            response = await ollama.generate(
                model=model,
                prompt=prompt,
                options={
                    "temperature": 0.3,
                    "num_predict": 4000
                }
            )

            generated_text = response.get('response', '')

            # Parse the response to extract files
            gitlab_ci = self._extract_code_block(generated_text, 'gitlab-ci')
            dockerfile = self._extract_code_block(generated_text, 'dockerfile')

            # If extraction failed, try alternative patterns
            if not gitlab_ci:
                gitlab_ci = self._extract_yaml_content(generated_text)
            if not dockerfile:
                dockerfile = self._extract_dockerfile_content(generated_text)

            return {
                "gitlab_ci": gitlab_ci or self._get_default_gitlab_ci(analysis),
                "dockerfile": dockerfile or self._get_default_dockerfile(analysis),
                "analysis": analysis,
                "model_used": model,
                "feedback_used": len(feedback)
            }
        finally:
            await ollama.close()

    def _extract_code_block(self, text: str, block_type: str) -> Optional[str]:
        """Extract code block from markdown-style response"""
        patterns = [
            rf'```{block_type}\n(.*?)```',
            rf'```{block_type}\s*\n(.*?)```',
            rf'```yaml\n(.*?)```' if block_type == 'gitlab-ci' else rf'```dockerfile\n(.*?)```'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_yaml_content(self, text: str) -> Optional[str]:
        """Extract YAML content using various patterns"""
        # Look for stages: keyword which indicates gitlab-ci
        match = re.search(r'(stages:.*?)(?=```|$)', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return None

    def _extract_dockerfile_content(self, text: str) -> Optional[str]:
        """Extract Dockerfile content"""
        match = re.search(r'(FROM\s+\S+.*?)(?=```|$)', text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _get_default_gitlab_ci(self, analysis: Dict[str, Any]) -> str:
        """Get default gitlab-ci.yml based on analysis"""
        language = analysis['language']

        templates = {
            'python': '''stages:
  - build
  - test
  - security
  - deploy

variables:
  DOCKER_IMAGE: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA

build:
  stage: build
  image: docker:latest
  services:
    - docker:dind
  script:
    - docker build -t $DOCKER_IMAGE .
    - docker push $DOCKER_IMAGE

test:
  stage: test
  image: python:3.11
  script:
    - pip install -r requirements.txt
    - pip install pytest
    - pytest tests/ -v

security:
  stage: security
  image: aquasec/trivy:latest
  script:
    - trivy image --exit-code 1 --severity HIGH,CRITICAL $DOCKER_IMAGE
  allow_failure: true

deploy:
  stage: deploy
  script:
    - echo "Deploying to production..."
  only:
    - main
''',
            'javascript': '''stages:
  - build
  - test
  - security
  - deploy

variables:
  DOCKER_IMAGE: $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA

build:
  stage: build
  image: node:18
  script:
    - npm ci
    - npm run build
  artifacts:
    paths:
      - dist/

test:
  stage: test
  image: node:18
  script:
    - npm ci
    - npm test

security:
  stage: security
  image: aquasec/trivy:latest
  script:
    - trivy fs --exit-code 1 --severity HIGH,CRITICAL .
  allow_failure: true

deploy:
  stage: deploy
  script:
    - echo "Deploying to production..."
  only:
    - main
'''
        }

        return templates.get(language, templates['python'])

    def _get_default_dockerfile(self, analysis: Dict[str, Any]) -> str:
        """Get default Dockerfile based on analysis"""
        language = analysis['language']

        templates = {
            'python': '''FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
''',
            'javascript': '''FROM node:18-alpine as builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:18-alpine
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY . .

EXPOSE 3000
CMD ["npm", "start"]
'''
        }

        return templates.get(language, templates['python'])

    async def commit_to_gitlab(
        self,
        repo_url: str,
        gitlab_token: str,
        files: Dict[str, str],
        branch_name: str,
        commit_message: str = "Add CI/CD pipeline configuration"
    ) -> Dict[str, Any]:
        """
        Commit generated files to a new branch in GitLab.

        Args:
            repo_url: GitLab repository URL
            gitlab_token: GitLab access token
            files: Dict of filename -> content
            branch_name: Name for the new branch
            commit_message: Commit message
        """
        parsed = self.parse_gitlab_url(repo_url)

        async with httpx.AsyncClient() as client:
            headers = {
                "PRIVATE-TOKEN": gitlab_token,
                "Content-Type": "application/json"
            }

            # Get default branch
            project_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}"
            project_resp = await client.get(project_url, headers=headers)
            project_resp.raise_for_status()
            project = project_resp.json()
            default_branch = project.get('default_branch', 'main')

            # Create commit with new branch
            actions = []
            for filename, content in files.items():
                # Check if file exists
                file_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/files/{filename.replace('/', '%2F')}"
                file_resp = await client.get(
                    file_url,
                    headers=headers,
                    params={"ref": default_branch}
                )

                action = "update" if file_resp.status_code == 200 else "create"
                actions.append({
                    "action": action,
                    "file_path": filename,
                    "content": content
                })

            # Create commit
            commit_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/commits"
            commit_data = {
                "branch": branch_name,
                "start_branch": default_branch,
                "commit_message": commit_message,
                "actions": actions
            }

            commit_resp = await client.post(commit_url, headers=headers, json=commit_data)
            commit_resp.raise_for_status()
            commit = commit_resp.json()

            return {
                "success": True,
                "commit_id": commit.get('id'),
                "branch": branch_name,
                "web_url": commit.get('web_url'),
                "project_id": project['id']
            }

    async def get_pipeline_status(
        self,
        repo_url: str,
        gitlab_token: str,
        branch: str
    ) -> Dict[str, Any]:
        """Get the latest pipeline status for a branch"""
        parsed = self.parse_gitlab_url(repo_url)

        async with httpx.AsyncClient() as client:
            headers = {"PRIVATE-TOKEN": gitlab_token}

            # Get pipelines for the branch
            pipelines_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines"
            resp = await client.get(
                pipelines_url,
                headers=headers,
                params={"ref": branch, "per_page": 1}
            )
            resp.raise_for_status()
            pipelines = resp.json()

            if not pipelines:
                return {"status": "no_pipeline", "message": "No pipeline found for this branch"}

            pipeline = pipelines[0]

            # Get detailed pipeline info
            pipeline_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines/{pipeline['id']}"
            detail_resp = await client.get(pipeline_url, headers=headers)
            detail = detail_resp.json()

            # Get jobs if pipeline failed
            jobs = []
            if pipeline['status'] in ['failed', 'canceled']:
                jobs_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines/{pipeline['id']}/jobs"
                jobs_resp = await client.get(jobs_url, headers=headers)
                jobs = jobs_resp.json()

            return {
                "pipeline_id": pipeline['id'],
                "status": pipeline['status'],
                "web_url": pipeline.get('web_url'),
                "created_at": pipeline.get('created_at'),
                "finished_at": detail.get('finished_at'),
                "duration": detail.get('duration'),
                "failed_jobs": [
                    {"name": j['name'], "stage": j['stage'], "status": j['status']}
                    for j in jobs if j['status'] == 'failed'
                ]
            }

    async def store_feedback(
        self,
        original_gitlab_ci: str,
        corrected_gitlab_ci: str,
        original_dockerfile: str,
        corrected_dockerfile: str,
        language: str,
        framework: str,
        error_type: str,
        fix_description: str
    ) -> bool:
        """
        Store feedback from manual corrections for reinforcement learning.
        """
        try:
            chromadb = self._get_chromadb()

            # Ensure collection exists
            collection = await chromadb.get_collection(self.FEEDBACK_COLLECTION)
            if not collection:
                await chromadb.create_collection(
                    self.FEEDBACK_COLLECTION,
                    metadata={"description": "Pipeline generation feedback for RL"}
                )

            # Generate unique ID based on content
            content_hash = hashlib.md5(
                f"{original_gitlab_ci}{corrected_gitlab_ci}".encode()
            ).hexdigest()[:12]

            # Create feedback document
            feedback_doc = f"""
## Original GitLab CI:
```yaml
{original_gitlab_ci[:500]}...
```

## Corrected GitLab CI:
```yaml
{corrected_gitlab_ci[:500]}...
```

## Error Type: {error_type}
## Fix Description: {fix_description}

## Key Changes:
- Language: {language}
- Framework: {framework}
"""

            # Store in ChromaDB
            await chromadb.add_documents(
                collection_id=self.FEEDBACK_COLLECTION,
                ids=[f"feedback_{content_hash}_{datetime.now().strftime('%Y%m%d%H%M%S')}"],
                documents=[feedback_doc],
                metadatas=[{
                    "language": language,
                    "framework": framework,
                    "error_type": error_type,
                    "fix_description": fix_description,
                    "timestamp": datetime.now().isoformat()
                }]
            )

            await chromadb.close()
            return True
        except Exception as e:
            print(f"Error storing feedback: {e}")
            return False

    async def compare_and_learn(
        self,
        repo_url: str,
        gitlab_token: str,
        branch: str,
        generated_files: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Compare current files in repo with generated files and learn from differences.
        Called after manual fixes to learn from corrections.
        """
        parsed = self.parse_gitlab_url(repo_url)

        async with httpx.AsyncClient() as client:
            headers = {"PRIVATE-TOKEN": gitlab_token}

            differences = {}

            for filename, original_content in generated_files.items():
                # Get current file content from repo
                file_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/files/{filename.replace('/', '%2F')}/raw"
                resp = await client.get(
                    file_url,
                    headers=headers,
                    params={"ref": branch}
                )

                if resp.status_code == 200:
                    current_content = resp.text

                    if current_content.strip() != original_content.strip():
                        differences[filename] = {
                            "original": original_content,
                            "corrected": current_content,
                            "changed": True
                        }
                    else:
                        differences[filename] = {"changed": False}

            return differences


# Singleton instance
pipeline_generator = PipelineGeneratorService()
