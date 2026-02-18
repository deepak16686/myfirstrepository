"""
File: generator.py
Purpose: Facade class (GitHubPipelineGeneratorService) that orchestrates the entire GitHub Actions
    pipeline generation lifecycle. Delegates to analyzer, templates, validator, default_templates,
    committer, and status modules while providing the core generate_workflow_files() and
    generate_with_validation() methods that implement the 4-tier priority system (ChromaDB proven
    template > built-in default > LLM generation > fallback default).
When Used: Instantiated as a singleton in __init__.py and used by the GitHub pipeline router for
    every operation: /generate, /generate-validated, /commit, /status, /learn, and the /chat
    endpoint's pipeline generation flow.
Why Created: Acts as the single entry point for the package after the original monolithic
    github_pipeline_generator.py (1564 lines) was split into 7+ specialized modules. Keeps the
    public API stable while allowing internal modules to evolve independently.
"""
import re
from typing import Dict, Any, Optional

from app.config import settings
from app.integrations.llm_provider import get_llm_provider, get_active_provider_name

from app.services.github_pipeline.analyzer import (
    parse_github_url,
    analyze_repository,
    _detect_language,
    _detect_framework,
    _detect_package_manager,
)
from app.services.github_pipeline.templates import (
    FEEDBACK_COLLECTION,
    TEMPLATES_COLLECTION,
    SUCCESSFUL_PIPELINES_COLLECTION,
    _ensure_learn_job,
    get_reference_workflow,
    get_best_template_files,
)
from app.services.github_pipeline.validator import (
    _validate_and_fix_workflow,
    _validate_and_fix_dockerfile,
)
from app.services.github_pipeline.default_templates import (
    _get_default_workflow,
    _get_default_dockerfile,
    _get_java_workflow_template,
    _get_python_workflow_template,
    _get_nodejs_workflow_template,
    _get_go_workflow_template,
)
from app.services.github_pipeline.committer import commit_to_github
from app.services.github_pipeline.status import (
    get_workflow_status,
    record_workflow_result,
)


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

    FEEDBACK_COLLECTION = FEEDBACK_COLLECTION
    TEMPLATES_COLLECTION = TEMPLATES_COLLECTION
    SUCCESSFUL_PIPELINES_COLLECTION = SUCCESSFUL_PIPELINES_COLLECTION
    DEFAULT_MODEL = "pipeline-generator-v5"

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

    # --- Delegation to analyzer module ---

    def parse_github_url(self, url: str) -> Dict[str, str]:
        """Parse GitHub/Gitea repository URL to extract owner and repo"""
        return parse_github_url(url)

    async def analyze_repository(
        self,
        repo_url: str,
        github_token: str
    ) -> Dict[str, Any]:
        """Analyze repository to detect language, framework, and structure"""
        return await analyze_repository(repo_url, github_token)

    def _detect_language(self, files):
        """Detect primary programming language"""
        return _detect_language(files)

    def _detect_framework(self, files):
        """Detect framework"""
        return _detect_framework(files)

    def _detect_package_manager(self, files):
        """Detect package manager"""
        return _detect_package_manager(files)

    # --- Delegation to templates module ---

    def _ensure_learn_job(self, workflow: str) -> str:
        """Ensure the learn-record job exists in the workflow"""
        return _ensure_learn_job(workflow)

    async def get_reference_workflow(
        self,
        language: str,
        framework: Optional[str] = None
    ) -> Optional[str]:
        """Get reference workflow from ChromaDB"""
        return await get_reference_workflow(language, framework)

    async def get_best_template_files(
        self,
        language: str,
        framework: Optional[str] = None
    ) -> Optional[Dict[str, str]]:
        """Get the best performing template from successful pipelines"""
        return await get_best_template_files(language, framework)

    # --- Delegation to validator module ---

    def _validate_and_fix_workflow(
        self,
        workflow: str,
        reference: Optional[str]
    ) -> str:
        """Validate and fix common issues in generated workflow"""
        return _validate_and_fix_workflow(workflow, reference)

    def _validate_and_fix_dockerfile(self, dockerfile: str, language: str) -> str:
        """Validate and fix Dockerfile"""
        return _validate_and_fix_dockerfile(dockerfile, language)

    # --- Delegation to default_templates module ---

    def _get_default_workflow(self, analysis: Dict[str, Any], runner_type: str = "self-hosted") -> str:
        """Get default GitHub Actions workflow template"""
        return _get_default_workflow(analysis, runner_type)

    def _get_java_workflow_template(self, runner_type: str = "self-hosted") -> str:
        """Java workflow template"""
        return _get_java_workflow_template(runner_type)

    def _get_python_workflow_template(self, runner_type: str = "self-hosted") -> str:
        """Python workflow template"""
        return _get_python_workflow_template(runner_type)

    def _get_nodejs_workflow_template(self, runner_type: str = "self-hosted") -> str:
        """Node.js workflow template"""
        return _get_nodejs_workflow_template(runner_type)

    def _get_go_workflow_template(self, runner_type: str = "self-hosted") -> str:
        """Go workflow template"""
        return _get_go_workflow_template(runner_type)

    def _get_default_dockerfile(self, analysis: Dict[str, Any]) -> str:
        """Get default Dockerfile based on language"""
        return _get_default_dockerfile(analysis)

    # --- Delegation to committer module ---

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
        return await commit_to_github(
            repo_url, github_token, workflow, dockerfile,
            branch_name, commit_message
        )

    # --- Delegation to status module ---

    async def get_workflow_status(
        self,
        repo_url: str,
        github_token: str,
        branch: str
    ) -> Dict[str, Any]:
        """Get latest workflow run status"""
        return await get_workflow_status(repo_url, github_token, branch)

    async def record_workflow_result(
        self,
        repo_url: str,
        github_token: str,
        branch: str,
        run_id: int
    ) -> Dict[str, Any]:
        """Record successful workflow for RL"""
        return await record_workflow_result(repo_url, github_token, branch, run_id)

    # --- Delegation to parse helper ---

    def parse_repo_url(self, url: str) -> Dict[str, str]:
        """Alias for parse_github_url for consistency with Jenkins API"""
        return parse_github_url(url)

    # --- Core generation methods (remain in facade) ---

    async def generate_with_validation(
        self,
        repo_url: str,
        github_token: str,
        model: str = None,
        max_fix_attempts: int = 10,
        additional_context: str = "",
        runner_type: str = "self-hosted"
    ) -> Dict[str, Any]:
        """
        Generate workflow + validate with iterative LLM fixing.
        Matches Jenkins generate_with_validation pattern.
        """
        from app.services.github_llm_fixer import github_llm_fixer
        from app.services.github_pipeline.image_seeder import ensure_images_in_nexus

        # Step 1: Generate workflow files (uses 3-tier priority)
        result = await self.generate_workflow_files(
            repo_url=repo_url,
            github_token=github_token,
            additional_context=additional_context,
            model=model,
            runner_type=runner_type
        )

        workflow = result["workflow"]
        dockerfile = result["dockerfile"]
        analysis = result["analysis"]
        model_used = result["model_used"]

        # Step 2: Run iterative LLM fixer (all sources go through validation now)
        fix_result = await github_llm_fixer.iterative_fix(
            workflow=workflow,
            dockerfile=dockerfile,
            analysis=analysis,
            max_attempts=max_fix_attempts,
            model=model
        )

        # Step 4: Auto-seed images
        try:
            await ensure_images_in_nexus(fix_result["workflow"])
        except Exception as e:
            print(f"[GitHub Pipeline] Image seeding warning: {e}")

        return {
            "success": True,
            "workflow": fix_result["workflow"],
            "dockerfile": fix_result["dockerfile"],
            "analysis": analysis,
            "model_used": model_used,
            "feedback_used": result.get("feedback_used", 0),
            "template_source": None,
            "validation_skipped": False,
            "validation_passed": fix_result.get("success", False),
            "validation_errors": fix_result.get("final_errors", []),
            "fix_attempts": fix_result.get("attempts", 0),
            "fix_history": fix_result.get("fix_history", []),
            "has_warnings": fix_result.get("has_warnings", False),
        }

    # Known languages with reliable built-in templates (Gitea Actions compatible)
    KNOWN_LANGUAGES = {"java", "python", "javascript", "go"}

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
        2. For known languages: use built-in defaults (Gitea-compatible)
        3. For unknown languages: use LLM generation
        4. Fallback: built-in default templates
        """
        # Analyze repository
        analysis = await self.analyze_repository(repo_url, github_token)
        language = analysis["language"]
        framework = analysis["framework"]

        print(f"[GitHub Pipeline] Analyzing {repo_url}: {language}/{framework}")

        # Priority 1: Check for proven successful template from ChromaDB (RL)
        best_template = await self.get_best_template_files(language, framework)
        if best_template and best_template.get("workflow"):
            print(f"[GitHub Pipeline] Using proven template from ChromaDB")
            workflow = self._ensure_learn_job(best_template["workflow"])
            dockerfile = best_template.get("dockerfile", self._get_default_dockerfile(analysis))

            # Rewrite template images to match this project's resolved versions
            from app.services.shared.deep_analyzer import rewrite_template_images
            workflow, dockerfile, rewrite_corrections = rewrite_template_images(
                workflow, dockerfile, analysis
            )
            if rewrite_corrections:
                print(f"[GitHub Pipeline] Rewrote {len(rewrite_corrections)} image(s): {rewrite_corrections}")

            return {
                "success": True,
                "workflow": workflow,
                "dockerfile": dockerfile,
                "analysis": analysis,
                "model_used": "chromadb-successful",
                "feedback_used": 0
            }

        # Priority 2: For known languages, use built-in defaults (Gitea-compatible)
        # LLM generates Gitea-incompatible patterns (wrong registries, docker login, etc.)
        if language in self.KNOWN_LANGUAGES or use_template_only:
            print(f"[GitHub Pipeline] Using built-in default template for {language}")
            workflow = self._get_default_workflow(analysis, runner_type)
            dockerfile = self._get_default_dockerfile(analysis)

            # Rewrite default template images to match this project's resolved versions
            from app.services.shared.deep_analyzer import rewrite_template_images
            workflow, dockerfile, rewrite_corrections = rewrite_template_images(
                workflow, dockerfile, analysis
            )
            if rewrite_corrections:
                print(f"[GitHub Pipeline] Rewrote {len(rewrite_corrections)} default template image(s): {rewrite_corrections}")

            return {
                "success": True,
                "workflow": self._ensure_learn_job(workflow),
                "dockerfile": dockerfile,
                "analysis": analysis,
                "model_used": "default-template",
                "feedback_used": 0
            }

        # Priority 3: Unknown language — try LLM generation
        try:
            reference = await self.get_reference_workflow(language, framework)
            generated = await self._generate_with_llm(
                analysis, reference, additional_context, model or self.DEFAULT_MODEL
            )

            if generated:
                workflow = self._validate_and_fix_workflow(generated.get("workflow", ""), reference)
                dockerfile = self._validate_and_fix_dockerfile(generated.get("dockerfile", ""), language)

                # Rewrite LLM-generated images to match this project's resolved versions
                from app.services.shared.deep_analyzer import rewrite_template_images
                workflow, dockerfile, rewrite_corrections = rewrite_template_images(
                    workflow, dockerfile, analysis
                )
                if rewrite_corrections:
                    print(f"[GitHub Pipeline] Rewrote {len(rewrite_corrections)} LLM image(s): {rewrite_corrections}")

                return {
                    "success": True,
                    "workflow": self._ensure_learn_job(workflow),
                    "dockerfile": dockerfile,
                    "analysis": analysis,
                    "model_used": get_active_provider_name(),
                    "feedback_used": 0
                }
        except Exception as e:
            print(f"[GitHub Pipeline] LLM generation failed: {e}")

        # Fallback: Use default templates
        print(f"[GitHub Pipeline] Falling back to built-in default template for {language}")
        workflow = self._get_default_workflow(analysis, runner_type)
        dockerfile = self._get_default_dockerfile(analysis)

        # Rewrite fallback template images to match this project's resolved versions
        from app.services.shared.deep_analyzer import rewrite_template_images
        workflow, dockerfile, rewrite_corrections = rewrite_template_images(
            workflow, dockerfile, analysis
        )
        if rewrite_corrections:
            print(f"[GitHub Pipeline] Rewrote {len(rewrite_corrections)} fallback image(s): {rewrite_corrections}")

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
        """Generate workflow using configured LLM provider"""
        prompt = self._build_generation_prompt(analysis, reference, additional_context)

        try:
            llm = get_llm_provider()
            response = await llm.generate(
                model=model,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 6000
                }
            )
            await llm.close()

            generated_text = response.get("response", "")
            return self._parse_llm_output(generated_text)

        except Exception as e:
            print(f"[LLM] Error: {e}")

        return None

    def _build_generation_prompt(
        self,
        analysis: Dict[str, Any],
        reference: Optional[str],
        additional_context: str
    ) -> str:
        """Build prompt for LLM generation"""
        # Build deep analysis context
        from app.services.shared.deep_analyzer import build_deep_context
        deep_context = build_deep_context(analysis)
        deep_section = f"\nDeep Analysis (from file content scanning):\n{deep_context}\n" if deep_context else ""

        prompt = f"""Generate a GitHub Actions workflow and Dockerfile for a {analysis['language']} project.

Project Analysis:
- Language: {analysis['language']}
- Framework: {analysis['framework']}
- Package Manager: {analysis['package_manager']}
{deep_section}
Requirements:
- Use Nexus private registry for ALL images: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/<image>
- Use self-hosted runners with access to internal network
- Include all 10 jobs: compile, build-image, test-image, static-analysis, sonarqube, trivy-scan, push-release, notify-success, notify-failure, learn-record
- Trigger on push to branches: [main, develop, 'feature/*', 'ci-pipeline-*']
- IMPORTANT Gitea Actions limitations:
  - Do NOT use actions/upload-artifact or actions/download-artifact (artifact service is broken on Gitea)
  - Do NOT use docker/build-push-action, docker/login-action, or docker/setup-buildx-action (not available on Gitea)
  - Each job must be self-contained (checkout its own code)
  - Use shell commands for docker: docker login, docker build, docker push
  - Container jobs use 'container: image:' block and need Node.js-enabled images for actions/checkout@v4
  - Non-container jobs (build-image, test-image, push-release) use shell docker commands directly
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
            result["dockerfile"] = self._strip_code_fences(dockerfile_match.group(1).strip())

        # Extract GitHub Actions workflow
        workflow_match = re.search(
            r'---GITHUB_ACTIONS---\s*(.*?)\s*---END---',
            text, re.DOTALL
        )
        if workflow_match:
            result["workflow"] = self._strip_code_fences(workflow_match.group(1).strip())

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

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Strip markdown code fences from extracted content."""
        # Remove opening fence like ```yaml, ```dockerfile, ```
        text = re.sub(r'^```\w*\s*\n?', '', text)
        # Remove closing fence
        text = re.sub(r'\n?```\s*$', '', text)
        return text.strip()
