"""
GitLab Pipeline Generator Service - Facade Class

This service handles:
1. Generating gitlab-ci.yml and Dockerfile using Ollama
2. Committing files to GitLab repositories
3. Monitoring pipeline status
4. Storing and retrieving feedback from ChromaDB for reinforcement learning

The class delegates to standalone functions in sibling modules while maintaining
backward compatibility with existing callers.
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
from app.integrations.llm_provider import get_llm_provider
from app.services.gitlab_dry_run_validator import gitlab_dry_run_validator, GitLabDryRunValidator
from app.services.gitlab_llm_fixer import gitlab_llm_fixer, GitLabLLMFixer

from .constants import (
    FEEDBACK_COLLECTION,
    TEMPLATES_COLLECTION,
    SUCCESSFUL_PIPELINES_COLLECTION,
    DEFAULT_MODEL,
    LANGUAGE_COMPILE_IMAGES,
    LANGUAGE_DOCKERFILE_IMAGES,
    LANGUAGE_RUNTIME_IMAGES,
    LANGUAGE_COMPILE_COMMANDS,
)


class PipelineGeneratorService:
    """Service for generating and managing GitLab pipelines with RL feedback"""

    # Expose constants as class attributes for backward compatibility
    FEEDBACK_COLLECTION = FEEDBACK_COLLECTION
    TEMPLATES_COLLECTION = TEMPLATES_COLLECTION
    SUCCESSFUL_PIPELINES_COLLECTION = SUCCESSFUL_PIPELINES_COLLECTION
    DEFAULT_MODEL = DEFAULT_MODEL
    LANGUAGE_COMPILE_IMAGES = LANGUAGE_COMPILE_IMAGES
    LANGUAGE_DOCKERFILE_IMAGES = LANGUAGE_DOCKERFILE_IMAGES
    LANGUAGE_RUNTIME_IMAGES = LANGUAGE_RUNTIME_IMAGES
    LANGUAGE_COMPILE_COMMANDS = LANGUAGE_COMPILE_COMMANDS

    def __init__(self):
        self.ollama_config = tools_manager.get_tool("ollama")
        self.chromadb_config = tools_manager.get_tool("chromadb")
        self.gitlab_base_url = settings.gitlab_url
        self.gitlab_token = settings.gitlab_token

    def _get_llm(self):
        """Get the configured LLM provider (Ollama or Claude Code)."""
        return get_llm_provider()

    def _get_chromadb(self) -> ChromaDBIntegration:
        return ChromaDBIntegration(self.chromadb_config)

    # ========================================================================
    # Delegated methods - these call standalone functions from sibling modules
    # ========================================================================

    def parse_gitlab_url(self, url: str) -> Dict[str, str]:
        from .analyzer import parse_gitlab_url
        return parse_gitlab_url(url)

    async def analyze_repository(self, repo_url: str, gitlab_token: str) -> Dict[str, Any]:
        from .analyzer import analyze_repository
        return await analyze_repository(repo_url, gitlab_token)

    def _detect_language(self, files: List[str]) -> str:
        from .analyzer import _detect_language
        return _detect_language(files)

    def _detect_framework(self, files: List[str]) -> str:
        from .analyzer import _detect_framework
        return _detect_framework(files)

    def _detect_package_manager(self, files: List[str]) -> str:
        from .analyzer import _detect_package_manager
        return _detect_package_manager(files)

    def _ensure_learn_stage(self, pipeline_yaml: str) -> str:
        from .validator import _ensure_learn_stage
        return _ensure_learn_stage(pipeline_yaml)

    def validate_and_fix_pipeline_images(
        self, gitlab_ci: str, dockerfile: str, language: str
    ) -> tuple:
        from .validator import validate_and_fix_pipeline_images
        return validate_and_fix_pipeline_images(gitlab_ci, dockerfile, language)

    def _validate_and_fix_pipeline(self, generated: str, reference: Optional[str]) -> str:
        from .validator import _validate_and_fix_pipeline
        return _validate_and_fix_pipeline(generated, reference)

    def _validate_and_fix_dockerfile(self, dockerfile: str, language: str) -> str:
        from .validator import _validate_and_fix_dockerfile
        return _validate_and_fix_dockerfile(dockerfile, language)

    def _extract_code_block(self, text: str, block_type: str) -> Optional[str]:
        from .validator import _extract_code_block
        return _extract_code_block(text, block_type)

    def _extract_yaml_content(self, text: str) -> Optional[str]:
        from .validator import _extract_yaml_content
        return _extract_yaml_content(text)

    def _extract_dockerfile_content(self, text: str) -> Optional[str]:
        from .validator import _extract_dockerfile_content
        return _extract_dockerfile_content(text)

    def _get_default_gitlab_ci(self, analysis: Dict[str, Any]) -> str:
        from .default_templates import _get_default_gitlab_ci
        return _get_default_gitlab_ci(analysis)

    def _get_default_dockerfile(self, analysis: Dict[str, Any]) -> str:
        from .default_templates import _get_default_dockerfile
        return _get_default_dockerfile(analysis)

    async def get_reference_pipeline(self, language: str, framework: str) -> Optional[str]:
        from .templates import get_reference_pipeline
        return await get_reference_pipeline(language, framework)

    async def get_best_pipeline_config(self, language: str, framework: str = "") -> Optional[str]:
        from .templates import get_best_pipeline_config
        return await get_best_pipeline_config(language, framework)

    async def get_best_template_files(self, language: str, framework: str = "") -> Optional[Dict[str, str]]:
        from .templates import get_best_template_files
        return await get_best_template_files(language, framework)

    async def _store_validated_template(
        self, gitlab_ci: str, dockerfile: str, language: str, framework: str
    ) -> bool:
        from .templates import _store_validated_template
        return await _store_validated_template(gitlab_ci, dockerfile, language, framework)

    async def store_manual_template(
        self, language: str, framework: str, gitlab_ci: str,
        dockerfile: Optional[str] = None, description: Optional[str] = None
    ) -> bool:
        from .templates import store_manual_template
        return await store_manual_template(language, framework, gitlab_ci, dockerfile, description)

    async def store_successful_pipeline(
        self, repo_url: str, gitlab_token: str, branch: str, pipeline_id: int,
        gitlab_ci_content: str, dockerfile_content: str, language: str, framework: str,
        duration: Optional[int] = None, stages_passed: Optional[List[str]] = None
    ) -> bool:
        from .templates import store_successful_pipeline
        return await store_successful_pipeline(
            repo_url, gitlab_token, branch, pipeline_id,
            gitlab_ci_content, dockerfile_content, language, framework,
            duration, stages_passed
        )

    async def get_successful_pipelines(
        self, language: str, framework: str = "", limit: int = 5
    ) -> List[Dict[str, Any]]:
        from .templates import get_successful_pipelines
        return await get_successful_pipelines(language, framework, limit)

    async def commit_to_gitlab(
        self, repo_url: str, gitlab_token: str, files: Dict[str, str],
        branch_name: str, commit_message: str = "Add CI/CD pipeline configuration"
    ) -> Dict[str, Any]:
        from .committer import commit_to_gitlab
        return await commit_to_gitlab(repo_url, gitlab_token, files, branch_name, commit_message)

    async def get_pipeline_status(
        self, repo_url: str, gitlab_token: str, branch: str
    ) -> Dict[str, Any]:
        from .monitor import get_pipeline_status
        return await get_pipeline_status(repo_url, gitlab_token, branch)

    async def get_relevant_feedback(self, language: str, framework: str, limit: int = 5) -> List[Dict[str, Any]]:
        from .learning import get_relevant_feedback
        return await get_relevant_feedback(language, framework, limit)

    async def store_feedback(
        self, original_gitlab_ci: str, corrected_gitlab_ci: str,
        original_dockerfile: str, corrected_dockerfile: str,
        language: str, framework: str, error_type: str, fix_description: str
    ) -> bool:
        from .learning import store_feedback
        return await store_feedback(
            original_gitlab_ci, corrected_gitlab_ci,
            original_dockerfile, corrected_dockerfile,
            language, framework, error_type, fix_description
        )

    async def record_pipeline_result(
        self, repo_url: str, gitlab_token: str, branch: str, pipeline_id: int
    ) -> Dict[str, Any]:
        from .learning import record_pipeline_result
        return await record_pipeline_result(repo_url, gitlab_token, branch, pipeline_id)

    async def compare_and_learn(
        self, repo_url: str, gitlab_token: str, branch: str,
        generated_files: Dict[str, str]
    ) -> Dict[str, Any]:
        from .learning import compare_and_learn
        return await compare_and_learn(repo_url, gitlab_token, branch, generated_files)

    # ========================================================================
    # Core generation methods - kept in the facade as they orchestrate everything
    # ========================================================================

    async def generate_pipeline_files(
        self,
        repo_url: str,
        gitlab_token: str,
        additional_context: str = "",
        model: str = None,
        use_template_only: bool = False
    ) -> Dict[str, str]:
        """
        Generate .gitlab-ci.yml and Dockerfile using Ollama with RL feedback.
        Uses the pipeline-generator-v2 model with 8-stage pipeline knowledge.

        If use_template_only=True, skips LLM and returns default templates directly.
        """
        # Use default model if not specified
        if model is None:
            model = self.DEFAULT_MODEL

        # Analyze repository
        analysis = await self.analyze_repository(repo_url, gitlab_token)

        # If use_template_only, skip LLM and return default templates directly
        if use_template_only:
            print(f"[Template Mode] Returning default templates for {analysis['language']}")
            gitlab_ci = self._get_default_gitlab_ci(analysis)
            # Ensure learn stage is present for RL
            gitlab_ci = self._ensure_learn_stage(gitlab_ci)
            dockerfile = self._get_default_dockerfile(analysis)
            return {
                'gitlab_ci': gitlab_ci,
                'dockerfile': dockerfile,
                'analysis': analysis,
                'model_used': 'template-only',
                'feedback_used': 0
            }

        # ===================================================================
        # PRIORITY 1: Check ChromaDB for PROVEN templates
        # - Ollama: Use template DIRECTLY without LLM (Ollama tends to ignore templates)
        # - Claude Code: Pass template as mandatory reference to Claude for adaptation
        # ===================================================================
        print(f"[RL-Direct] Checking for proven templates for {analysis['language']}/{analysis['framework']}...")
        template_files = await self.get_best_template_files(
            analysis['language'],
            analysis['framework']
        )

        if template_files and template_files.get('gitlab_ci'):
            has_dockerfile = bool(template_files.get('dockerfile'))

            # Use proven template DIRECTLY when:
            # - It's an exact language match (not cross-language)
            # - It has both .gitlab-ci.yml AND Dockerfile
            # This avoids LLM re-generation which can introduce regressions.
            if has_dockerfile:
                print("[RL-Direct] Found proven template with Dockerfile! Using DIRECTLY (no LLM).")
                gitlab_ci = template_files['gitlab_ci']
                dockerfile = template_files['dockerfile']

                # Validate and fix images even for proven templates — stored templates
                # may use outdated image versions (e.g., golang:1.21 when project needs 1.22)
                gitlab_ci, dockerfile, img_corrections = self.validate_and_fix_pipeline_images(
                    gitlab_ci, dockerfile, analysis['language']
                )
                if img_corrections:
                    print(f"[RL-Direct] Fixed {len(img_corrections)} image(s) in proven template: {img_corrections}")

                # Auto-seed any missing images into Nexus
                from .image_seeder import ensure_images_in_nexus
                try:
                    print("[ImageSeeder] Running image seeder for chromadb-direct pipeline...")
                    seed_result = await ensure_images_in_nexus(gitlab_ci)
                    if seed_result.get('seeded'):
                        print(f"[ImageSeeder] Seeded {len(seed_result['seeded'])} images to Nexus: {seed_result['seeded']}")
                    if seed_result.get('failed'):
                        print(f"[ImageSeeder] Failed to seed: {seed_result['failed']}")
                except Exception as e:
                    print(f"[ImageSeeder] Warning: {e}")

                return {
                    'gitlab_ci': gitlab_ci,
                    'dockerfile': dockerfile,
                    'analysis': analysis,
                    'model_used': 'chromadb-direct',
                    'feedback_used': 0,
                    'template_source': 'reinforcement_learning'
                }
            else:
                # Template has .gitlab-ci.yml but no Dockerfile — pass to LLM as reference
                print("[RL+Claude] Found proven template (no Dockerfile). Passing to LLM as reference.")
        else:
            template_files = None

        if not template_files:
            print("[RL-Direct] No proven template found in ChromaDB...")

        # ===================================================================
        # PRIORITY 2: Use LLM to generate (Claude adapts RAG template, Ollama from scratch)
        # ===================================================================
        language = analysis.get('language', 'unknown').lower()

        # If Claude Code has a proven template from Priority 1, use it as the reference
        ref_source_language = language  # Track which language the reference came from
        if template_files and template_files.get('gitlab_ci'):
            reference_pipeline = template_files['gitlab_ci']
            print(f"[RL+Claude] Passing proven RAG template as reference to Claude for {language}...")
        else:
            print(f"[LLM-Generate] No RAG template for {language}. LLM is creating a new pipeline...")
            # Fallback: query ChromaDB for a reference pipeline (may be cross-language)
            reference_pipeline, ref_source_language = await self.get_reference_pipeline(
                analysis['language'],
                analysis['framework']
            )

        # Get relevant feedback from previous corrections
        feedback = await self.get_relevant_feedback(
            analysis['language'],
            analysis['framework']
        )

        # Build reference context - MANDATORY template from ChromaDB
        reference_context = ""
        template_available = False
        is_cross_language = ref_source_language and ref_source_language.lower() != language.lower()
        if reference_pipeline:
            template_available = True
            # Cross-language adaptation note
            if is_cross_language:
                cross_lang_note = (
                    f"\nNOTE: This reference template is from a {ref_source_language.upper()} project.\n"
                    f"You are generating for {language.upper()}. You MUST:\n"
                    f"- KEEP the exact structure: all 9 stages, variables, build_image, security, push, notify_success, notify_failure, learn_record\n"
                    f"- KEEP all infrastructure jobs EXACTLY as-is (Kaniko auth, Trivy services, Splunk HEC curl, learn_record curl)\n"
                    f"- ONLY change: compile/test/sast job images and commands for {language}\n"
                    f"- Use the correct {language} base image from Nexus for compile/test/sast stages\n"
                )
            else:
                cross_lang_note = ""
            reference_context = f"""
\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557
\u2551  MANDATORY REFERENCE TEMPLATE - YOU MUST USE THIS EXACT STRUCTURE            \u2551
\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d

The following is a PROVEN, WORKING pipeline template from our database.
You MUST use this as your base and ONLY modify language-specific parts.
{cross_lang_note}
```yaml
{reference_pipeline}
```

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
"""

        # Build feedback context
        feedback_context = ""
        if feedback:
            feedback_context = "\n\n## LEARNED CORRECTIONS (Apply these fixes):\n"
            for i, fb in enumerate(feedback, 1):
                feedback_context += f"""
### Fix {i}: {fb.get('error_type', 'N/A')}
- Problem: {fb.get('feedback', 'N/A')}
- Solution: {fb.get('fix_description', 'N/A')}
"""

        # Generate STRICT prompt with guardrails
        # Pre-compute conditional strings outside f-string (Python 3.11 doesn't allow backslashes in f-string expressions)
        template_warning = (
            "\u26a0\ufe0f  CRITICAL: A reference template was provided above. You MUST copy its structure exactly!"
            if template_available else
            "\u26a0\ufe0f  No template found - use the mandatory patterns below strictly."
        )
        additional_context_line = f"Additional context: {additional_context}" if additional_context else ""
        project_files_str = ', '.join(analysis['files'][:15])

        prompt = f"""
\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557
\u2551                    GITLAB CI/CD PIPELINE GENERATOR                            \u2551
\u2551                         STRICT MODE ENABLED                                   \u2551
\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d

## YOUR TASK:
Generate .gitlab-ci.yml and Dockerfile for a {analysis['language']} {analysis['framework']} project.

## PROJECT ANALYSIS:
- Language: {analysis['language']}
- Framework: {analysis['framework']}
- Package Manager: {analysis['package_manager']}
- Project Files: {project_files_str}

{reference_context}

{template_warning}

{feedback_context}

## \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
## STRICT GUARDRAILS - VIOLATION OF THESE RULES IS NOT ALLOWED
## \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

### RULE 1: EXACTLY 8 STAGES (in this exact order)
stages:
  - compile    # Build artifacts (JAR/dist/binary)
  - build      # Docker image with Kaniko
  - test       # Verify image in registry
  - sast       # Static security analysis
  - quality    # SonarQube code quality
  - security   # Trivy container scan
  - push       # Tag and push release
  - notify     # Splunk notifications

### RULE 2: MANDATORY VARIABLES BLOCK
variables:
  RELEASE_TAG: "1.0.release-${{CI_PIPELINE_IID}}"
  NEXUS_REGISTRY: "localhost:5001"
  NEXUS_PULL_REGISTRY: "localhost:5001"
  NEXUS_INTERNAL_REGISTRY: "ai-nexus:5001"
  IMAGE_NAME: "${{CI_PROJECT_NAME}}"
  IMAGE_TAG: "1.0.${{CI_PIPELINE_IID}}"
  DOCKER_TLS_CERTDIR: ""
  DOCKER_HOST: tcp://docker:2375
  FF_NETWORK_PER_BUILD: "true"
  SONARQUBE_URL: "http://ai-sonarqube:9000"
  SPLUNK_HEC_URL: "http://ai-splunk:8088"

### RULE 3: ALL JOBS MUST HAVE
- tags: [docker]
- image: must use ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/<image>:<tag> format
- Each job definition must be on its own line starting with the job name followed by colon

### RULE 4: REGISTRY USAGE (CRITICAL)
- NEXUS_PULL_REGISTRY (localhost:5001): Used for pulling job images (Docker Desktop can access this)
- NEXUS_INTERNAL_REGISTRY (ai-nexus:5001): Used for Kaniko pushes inside job containers
- For job image: field, ALWAYS use ${{NEXUS_PULL_REGISTRY}}
- For Kaniko destination, use ${{NEXUS_INTERNAL_REGISTRY}}
- Add --insecure-registry=ai-nexus:5001 to Kaniko command
- SonarQube: http://ai-sonarqube:9000
- Splunk HEC: http://ai-splunk:8088
- Trivy: trivy-server:8080 (as service alias)

### RULE 5: CREDENTIALS FROM GITLAB CI/CD VARIABLES
- ${{NEXUS_USERNAME}} and ${{NEXUS_PASSWORD}} for Nexus auth
- ${{SONAR_TOKEN}} for SonarQube
- ${{SPLUNK_HEC_TOKEN}} for Splunk HEC

### RULE 6: KANIKO BUILD JOB FORMAT (EXACT STRUCTURE)
build:
  stage: build
  image:
    name: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/kaniko-executor:debug
    entrypoint: [""]
  tags: [docker]
  script:
    - mkdir -p /kaniko/.docker
    - echo "{{\\"auths\\":{{\\"${{NEXUS_INTERNAL_REGISTRY}}\\":{{\\"username\\":\\"${{NEXUS_USERNAME}}\\",\\"password\\":\\"${{NEXUS_PASSWORD}}\\"}}}}}}" > /kaniko/.docker/config.json
    - /kaniko/executor --context ${{CI_PROJECT_DIR}} --dockerfile ${{CI_PROJECT_DIR}}/Dockerfile --destination ${{NEXUS_INTERNAL_REGISTRY}}/apm-repo/demo/${{IMAGE_NAME}}:${{IMAGE_TAG}} --insecure --skip-tls-verify --insecure-registry=ai-nexus:5001

### RULE 7: TRIVY SECURITY JOB MUST HAVE
services:
  - name: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/aquasec-trivy:latest
    alias: trivy-server
    command: ["server", "--listen", "0.0.0.0:8080"]

### RULE 8: NOTIFY STAGE MUST HAVE TWO JOBS
- notify_success: with "when: on_success"
- notify_failure: with "when: on_failure"

## \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
## DOCKERFILE RULES - MANDATORY FOR ALL DOCKERFILES
## \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

### RULE 9: ALL IMAGES MUST COME FROM NEXUS PRIVATE REGISTRY
- NEVER use public registries (docker.io, gcr.io, quay.io, etc.)
- ALL FROM statements MUST use: ai-nexus:5001/apm-repo/demo/
- Use ARG for registry to allow override

### RULE 10: DOCKERFILE MUST START WITH ARG AND FROM PATTERN
ARG BASE_REGISTRY=ai-nexus:5001
FROM ${{BASE_REGISTRY}}/apm-repo/demo/<image>:<tag>

### RULE 11: AVAILABLE BASE IMAGES IN NEXUS (use these ONLY)
- ai-nexus:5001/apm-repo/demo/amazoncorretto:17-alpine-jdk (Java)
- ai-nexus:5001/apm-repo/demo/python:3.11-slim (Python)
- ai-nexus:5001/apm-repo/demo/node:18-alpine (Node.js)
- ai-nexus:5001/apm-repo/demo/golang:1.21-alpine (Go)
- ai-nexus:5001/apm-repo/demo/alpine:3.18 (Alpine base)
- ai-nexus:5001/apm-repo/demo/nginx:alpine (Nginx)

### RULE 12: MULTI-STAGE BUILDS MUST USE NEXUS FOR ALL STAGES
Example:
ARG BASE_REGISTRY=ai-nexus:5001
FROM ${{BASE_REGISTRY}}/apm-repo/demo/node:18-alpine as builder
...
FROM ${{BASE_REGISTRY}}/apm-repo/demo/nginx:alpine
...

## \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
## OUTPUT FORMAT - FOLLOW EXACTLY
## \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

Return ONLY the following two code blocks. No explanations, no comments outside blocks.

```gitlab-ci
# Paste your complete .gitlab-ci.yml here
```

```dockerfile
# Paste your complete Dockerfile here
```

{additional_context_line}

REMEMBER: If a reference template was provided, COPY its structure exactly and only change language-specific commands.
DO NOT generate generic pipelines. Use the template from ChromaDB.
"""

        # Call LLM to generate with strict settings
        llm = self._get_llm()
        try:
            response = await llm.generate(
                model=model,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Very low for deterministic output
                    "num_predict": 6000,  # Increased for full pipeline
                    "top_p": 0.9,
                    "repeat_penalty": 1.1
                }
            )

            # FIX: Handle None response from LLM
            if response is None:
                return {
                    "gitlab_ci": self._get_default_gitlab_ci(analysis),
                    "dockerfile": self._get_default_dockerfile(analysis),
                    "analysis": analysis,
                    "model_used": model,
                    "feedback_used": len(feedback),
                    "error": "LLM returned empty response"
                }

            generated_text = response.get('response', '') if response else ''

            # Parse the response to extract files
            gitlab_ci = self._extract_code_block(generated_text, 'gitlab-ci')

            # Validate and fix the generated pipeline
            if gitlab_ci:
                gitlab_ci = self._validate_and_fix_pipeline(gitlab_ci, reference_pipeline)
            dockerfile = self._extract_code_block(generated_text, 'dockerfile')

            # Validate and fix the generated Dockerfile
            if dockerfile:
                dockerfile = self._validate_and_fix_dockerfile(dockerfile, analysis['language'])

            # If extraction failed, try alternative patterns
            if not gitlab_ci:
                gitlab_ci = self._extract_yaml_content(generated_text)
                # IMPORTANT: Validate fallback-extracted content too!
                if gitlab_ci:
                    gitlab_ci = self._validate_and_fix_pipeline(gitlab_ci, reference_pipeline)
            if not dockerfile:
                dockerfile = self._extract_dockerfile_content(generated_text)
                # IMPORTANT: Validate fallback-extracted content too!
                if dockerfile:
                    dockerfile = self._validate_and_fix_dockerfile(dockerfile, analysis['language'])

            # Get final gitlab_ci (use default if extraction failed)
            final_gitlab_ci = gitlab_ci or self._get_default_gitlab_ci(analysis)
            # Ensure learn stage is present for RL
            final_gitlab_ci = self._ensure_learn_stage(final_gitlab_ci)
            final_dockerfile = dockerfile or self._get_default_dockerfile(analysis)

            # Validate and auto-correct images for the detected language
            final_gitlab_ci, final_dockerfile, img_corrections = self.validate_and_fix_pipeline_images(
                final_gitlab_ci, final_dockerfile, analysis['language']
            )

            # Auto-seed any missing images into Nexus
            from .image_seeder import ensure_images_in_nexus
            try:
                print("[ImageSeeder] Running image seeder for LLM-generated pipeline...")
                seed_result = await ensure_images_in_nexus(final_gitlab_ci)
                if seed_result.get('seeded'):
                    print(f"[ImageSeeder] Seeded {len(seed_result['seeded'])} images to Nexus: {seed_result['seeded']}")
                if seed_result.get('failed'):
                    print(f"[ImageSeeder] Failed to seed: {seed_result['failed']}")
            except Exception as e:
                print(f"[ImageSeeder] Warning: {e}")

            # Track which LLM provider was used
            if settings.llm_provider == "claude-code":
                if template_files:
                    used_model = f"claude-rag-{settings.claude_model}"
                else:
                    used_model = f"claude-{settings.claude_model}"
            else:
                used_model = model

            return {
                "gitlab_ci": final_gitlab_ci,
                "dockerfile": final_dockerfile,
                "analysis": analysis,
                "model_used": used_model,
                "feedback_used": len(feedback)
            }
        finally:
            await llm.close()

    async def generate_with_validation(
        self,
        repo_url: str,
        gitlab_token: str,
        additional_context: str = "",
        model: str = None,
        max_fix_attempts: int = 3,
        store_on_success: bool = True
    ) -> Dict[str, Any]:
        """
        Generate pipeline files with dry-run validation and automatic fixing.

        This method:
        1. First checks ChromaDB for existing templates
        2. If no template, generates using LLM
        3. Validates the generated pipeline using GitLab CI lint
        4. If validation fails, uses LLM to fix and retries
        5. If successful, stores in ChromaDB for future use

        Args:
            repo_url: GitLab repository URL
            gitlab_token: GitLab API token
            additional_context: Additional context for generation
            model: Ollama model to use
            max_fix_attempts: Maximum number of fix attempts
            store_on_success: Whether to store successful pipelines in ChromaDB

        Returns:
            Dict with pipeline files, validation results, and metadata
        """
        model = model or self.DEFAULT_MODEL
        parsed = self.parse_gitlab_url(repo_url)
        project_path = parsed['path']

        # Step 1: Generate initial pipeline
        print(f"[Validation Flow] Generating pipeline for {repo_url}...")
        result = await self.generate_pipeline_files(
            repo_url=repo_url,
            gitlab_token=gitlab_token,
            additional_context=additional_context,
            model=model,
            use_template_only=False
        )

        gitlab_ci = result.get('gitlab_ci', '')
        dockerfile = result.get('dockerfile', '')
        analysis = result.get('analysis', {})

        # If template was used directly from ChromaDB, skip validation (already proven)
        if result.get('template_source') == 'reinforcement_learning':
            print("[Validation Flow] Using proven template from RL - skipping validation")
            return {
                **result,
                'validation_skipped': True,
                'validation_reason': 'Template from reinforcement learning (already validated)'
            }

        # Step 2: Validate the generated pipeline
        print("[Validation Flow] Running dry-run validation...")
        validator = gitlab_dry_run_validator

        validation_results = await validator.validate_all(
            gitlab_ci=gitlab_ci,
            dockerfile=dockerfile,
            gitlab_token=gitlab_token,
            project_path=project_path
        )

        all_valid, _ = validator.get_validation_summary(validation_results)

        # Collect errors
        all_errors = []
        all_warnings = []
        for check_name, check_result in validation_results.items():
            all_errors.extend([f"[{check_name}] {e}" for e in check_result.errors])
            all_warnings.extend([f"[{check_name}] {w}" for w in check_result.warnings])

        if all_valid or not all_errors:
            # Pipeline is valid or only has warnings
            print(f"[Validation Flow] Pipeline valid! (warnings: {len(all_warnings)})")

            # NOTE: Do NOT store template here. Dry-run validation only checks YAML syntax.
            # Templates are stored by the learn stage AFTER the pipeline actually succeeds in GitLab.
            # Storing here would save bad templates that fail at compile/build/test stages.

            return {
                **result,
                'validation_passed': True,
                'validation_results': {k: v.to_dict() for k, v in validation_results.items()},
                'warnings': all_warnings
            }

        # Step 3: Validation failed - attempt fixes
        print(f"[Validation Flow] Validation failed with {len(all_errors)} errors. Attempting fixes...")

        fixer = gitlab_llm_fixer
        fix_result = await fixer.iterative_fix(
            gitlab_ci=gitlab_ci,
            dockerfile=dockerfile,
            validator=validator,
            analysis=analysis,
            gitlab_token=gitlab_token,
            project_path=project_path,
            max_attempts=max_fix_attempts,
            model=model
        )

        if fix_result.get('success'):
            # Fixed successfully
            fixed_gitlab_ci = fix_result.get('gitlab_ci', gitlab_ci)
            fixed_dockerfile = fix_result.get('dockerfile', dockerfile)

            print(f"[Validation Flow] Pipeline fixed after {fix_result.get('attempts', 1)} attempt(s)")

            # NOTE: Do NOT store template here. Dry-run validation only checks YAML syntax.
            # Templates are stored by the learn stage AFTER the pipeline actually succeeds in GitLab.

            return {
                'gitlab_ci': fixed_gitlab_ci,
                'dockerfile': fixed_dockerfile,
                'analysis': analysis,
                'model_used': model,
                'feedback_used': result.get('feedback_used', 0),
                'validation_passed': True,
                'fix_attempts': fix_result.get('attempts', 1),
                'fix_history': fix_result.get('fix_history', []),
                'has_warnings': fix_result.get('has_warnings', False)
            }
        else:
            # Could not fix - return best effort
            print(f"[Validation Flow] Could not fix pipeline after {max_fix_attempts} attempts")
            return {
                'gitlab_ci': fix_result.get('gitlab_ci', gitlab_ci),
                'dockerfile': fix_result.get('dockerfile', dockerfile),
                'analysis': analysis,
                'model_used': model,
                'feedback_used': result.get('feedback_used', 0),
                'validation_passed': False,
                'validation_errors': fix_result.get('final_errors', all_errors),
                'fix_attempts': fix_result.get('attempts', max_fix_attempts),
                'fix_history': fix_result.get('fix_history', [])
            }
