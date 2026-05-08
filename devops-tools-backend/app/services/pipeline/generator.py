"""
GitLab Pipeline Generator Service - Facade Class

This service handles:
1. Generating gitlab-ci.yml and Dockerfile using the active LLM provider
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
from datetime import datetime, timezone
import httpx


# ---------------------------------------------------------------------------
# Template source banner — prepended to every generated gitlab_ci so engineers
# can see at a glance whether a pipeline came from RAG, LLM, or fallback.
# ---------------------------------------------------------------------------

# Maps the internal `model_used` token to a human-readable banner label.
PIPELINE_SOURCE_LABELS = {
    "chromadb-direct": "RAG (proven template from ChromaDB)",
    "rag-llm-adapt": "RAG + LLM (template adapted by LLM)",
    "rag-llm-adapt-fixed": "RAG + LLM + auto-fixer (template adapted, then validator-fixed)",
    "cross-language-rag": "RAG + LLM (cross-language template adapted by LLM)",
    "cross-language-rag-fixed": "RAG + LLM + auto-fixer (cross-language template adapted, then validator-fixed)",
    "llm-generate": "LLM-generated (no RAG match)",
    "generic-template-llm": "LLM-generated using Generic_template reference",
    "generic-template-llm-fixed": "LLM-generated using Generic_template + auto-fixer",
    "llm-fixer-loop": "LLM-generated + auto-fixer loop (no RAG match)",
    "direct-artifact-template": "Direct artifact template (chat-confirmed)",
    "template-only": "Default template (fallback)",
    "default-template": "Default template (fallback)",
}


def _format_source_label(token: str, has_rag_reference: bool) -> str:
    """Return a banner-friendly label given the internal `model_used` token.

    Falls back to a sensible default when the token is unknown (e.g. an LLM
    provider display name like ``"Codex Code (gpt-5.5)"``).
    """
    if not token:
        return "LLM-generated (no RAG match)" if not has_rag_reference else "RAG + LLM (template adapted by LLM)"
    label = PIPELINE_SOURCE_LABELS.get(token)
    if label:
        return label
    # Token is something like "Codex Code (gpt-5.5)" or "Ollama (llama3.1)" —
    # an LLM provider name. Distinguish by whether RAG influenced generation.
    return (
        "RAG + LLM (template adapted by LLM)" if has_rag_reference
        else "LLM-generated (no RAG match)"
    )


def _stamp_pipeline_source(
    gitlab_ci: str,
    source: str,
    generator: str,
) -> str:
    """Prepend a Pipeline Source banner comment to the gitlab-ci.yml content.

    If a banner is already present (idempotent re-stamping after a self-heal
    cycle), it is replaced rather than duplicated so the file stays clean.
    """
    if not gitlab_ci:
        return gitlab_ci

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    banner = (
        "# ╔══════════════════════════════════════════════════════════╗\n"
        f"# ║ Pipeline Source: {source:<46}║\n"
        f"# ║ Generator: {generator:<23} | Generated: {timestamp:<13}║\n"
        "# ╚══════════════════════════════════════════════════════════╝\n"
    )

    # Strip any existing banner (a contiguous block of lines starting with
    # the box-drawing prefix at the very top of the file).
    lines = gitlab_ci.split('\n')
    stripped: List[str] = []
    skipping_banner = True
    for line in lines:
        if skipping_banner and (
            line.startswith('# ╔') or
            line.startswith('# ║ Pipeline Source:') or
            line.startswith('# ║ Generator:') or
            line.startswith('# ╚')
        ):
            continue
        skipping_banner = False
        stripped.append(line)
    cleaned = '\n'.join(stripped).lstrip('\n')

    # Inject PIPELINE_SOURCE / PIPELINE_GENERATOR into the variables: block
    # so the learn_record job can echo them inside GitLab. Idempotent: replace
    # any existing pair, otherwise append after DEVOPS_BACKEND_URL.
    #
    # IMPORTANT: detection MUST match the *variable assignment* pattern
    # (start of line, indented, ending with quoted value) — not the bare
    # substring "PIPELINE_SOURCE:". The learn_record job legitimately
    # contains the literal `PIPELINE_SOURCE:-...` inside an echo statement,
    # which would otherwise cause us to skip the injection on first stamp.
    safe_source = source.replace('"', '\\"')
    safe_generator = generator.replace('"', '\\"')
    new_pipeline_vars = (
        f'  PIPELINE_SOURCE: "{safe_source}"\n'
        f'  PIPELINE_GENERATOR: "{safe_generator}"\n'
    )
    pipeline_var_pair_pattern = re.compile(
        r'^[ \t]+PIPELINE_SOURCE:[ \t]+"[^"]*"\s*\n'
        r'[ \t]+PIPELINE_GENERATOR:[ \t]+"[^"]*"\s*\n',
        flags=re.MULTILINE,
    )
    if pipeline_var_pair_pattern.search(cleaned):
        # Re-stamp path — replace the existing assignment pair in place
        cleaned = pipeline_var_pair_pattern.sub(
            new_pipeline_vars, cleaned, count=1,
        )
    else:
        # First stamp — append right after DEVOPS_BACKEND_URL when present,
        # otherwise immediately after the `variables:` header line.
        if re.search(r'^[ \t]+DEVOPS_BACKEND_URL:', cleaned, flags=re.MULTILINE):
            cleaned = re.sub(
                r'(^[ \t]+DEVOPS_BACKEND_URL:[^\n]*\n)',
                r'\1' + new_pipeline_vars,
                cleaned,
                count=1,
                flags=re.MULTILINE,
            )
        elif re.search(r'^variables:\s*$', cleaned, flags=re.MULTILINE):
            cleaned = re.sub(
                r'(^variables:\s*\n)',
                r'\1' + new_pipeline_vars,
                cleaned,
                count=1,
                flags=re.MULTILINE,
            )

    return banner + cleaned


def _disable_learn_recording_for_rag_hit(gitlab_ci: str) -> str:
    """Keep the learn stage green for direct RAG reuse without writing to RAG.

    Direct RAG hits are already served from ``gitlab_successful_template``.
    Re-recording those runs can recreate a template the operator just deleted
    while the GitLab pipeline is still running. LLM/self-heal generations keep
    the normal learn_record job and are the only path that repopulates RAG.
    """
    if not gitlab_ci or "learn_record:" not in gitlab_ci:
        return gitlab_ci

    lines = gitlab_ci.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "learn_record:":
            start = index
            break

    if start is None:
        return gitlab_ci

    end = len(lines)
    top_level_job = re.compile(r"^[A-Za-z0-9_.-][A-Za-z0-9_.-]*:\s*$")
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if top_level_job.match(line) and line.strip() != "learn_record:":
            end = index
            break

    noop_job = [
        "learn_record:",
        "  stage: learn",
        "  image: ${NEXUS_PULL_REGISTRY}/apm-repo/demo/curlimages-curl:latest",
        "  tags: [docker]",
        "  script:",
        '    - echo "RAG direct run - learning skipped because template already exists."',
        '    - echo "Delete from ChromaDB stays deleted until an LLM/self-heal run succeeds."',
        "  when: on_success",
        "  allow_failure: true",
    ]
    return "\n".join(lines[:start] + noop_job + lines[end:]) + "\n"

from app.config import settings, tools_manager
from app.integrations.ollama import OllamaIntegration
from app.integrations.chromadb import ChromaDBIntegration
from app.integrations.llm_provider import get_llm_provider, get_active_provider_name
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
        """Get the configured LLM provider."""
        return get_llm_provider()

    def _apply_pipeline_requirements(
        self,
        analysis: Dict[str, Any],
        pipeline_requirements: Optional[Dict[str, Any]],
    ) -> None:
        """Merge chatbot-confirmed pipeline requirements into repo analysis."""
        if not pipeline_requirements:
            return

        clean_requirements = {
            key: value
            for key, value in pipeline_requirements.items()
            if value not in (None, "", [], {})
        }
        analysis["pipeline_requirements"] = clean_requirements

        for key in (
            "output_mode",
            "dockerfile_strategy",
            "language_version",
            "java_version",
            "build_tool",
            "build_tool_version",
            "framework",
            "framework_version",
            "packaging",
            "module_type",
            "module_path",
            "artifact_pattern",
            "artifact_publish_target",
            "registry_strategy",
            "runner_type",
        ):
            if key in clean_requirements:
                analysis[key] = clean_requirements[key]

        if (
            str(analysis.get("language", "")).lower() == "java"
            and analysis.get("language_version")
            and not analysis.get("java_version")
        ):
            analysis["java_version"] = analysis["language_version"]

    def _is_direct_artifact_mode(self, analysis: Dict[str, Any]) -> bool:
        output_mode = str(analysis.get("output_mode") or "").replace("_", "-").lower()
        return output_mode in ("direct-artifact", "artifact", "artifact-only")

    def _get_direct_artifact_gradle_image(self, java_version: str) -> str:
        """Return a Gradle builder image known to exist in the local Nexus mirror."""
        normalized = str(java_version or "17").strip()
        known_images = {
            "8": "gradle:7.6-jdk8",
            "11": "gradle:8.7-jdk11",
            "17": "gradle:8.7-jdk17-alpine",
            "21": "gradle:8.12-jdk21",
        }
        return known_images.get(normalized, "gradle:8.12-jdk21")

    def _get_direct_artifact_gitlab_ci(self, analysis: Dict[str, Any]) -> str:
        """Create a CI pipeline that publishes artifacts without an image build."""
        language = str(analysis.get("language", "unknown")).lower()
        build_tool = str(
            analysis.get("build_tool") or analysis.get("package_manager") or ""
        ).lower()
        java_version = str(analysis.get("java_version") or analysis.get("language_version") or "17")

        if language == "java" and build_tool == "gradle":
            compile_image = self._get_direct_artifact_gradle_image(java_version)
        elif language == "java":
            compile_image = f"maven:3.9-eclipse-temurin-{java_version}"
        else:
            compile_image = (
                analysis.get("resolved_compile_image")
                or LANGUAGE_COMPILE_IMAGES.get(language, "alpine:3.18")
            )
        image_ref = f"${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/{compile_image}"

        compile_script, test_script, artifact_paths = self._get_direct_artifact_commands(analysis)
        artifact_target = str(analysis.get("artifact_publish_target") or "gitlab-artifacts")

        use_gitlab_artifacts = artifact_target in ("gitlab-artifacts", "job-artifacts")
        use_gitlab_packages = artifact_target in (
            "gitlab-packages",
            "gitlab-package-registry",
            "package-registry",
        )

        publish_script = [
            'echo "Publishing artifacts through GitLab job artifacts"',
            f'echo "Artifact target={artifact_target}"',
            'find . -maxdepth 4 -type f \\( -name "*.jar" -o -name "*.war" -o -name "*.zip" -o -name "*.tgz" -o -name "*.whl" \\) || true',
        ]
        if use_gitlab_packages:
            publish_script = compile_script + [
                'echo "Publishing artifacts to GitLab Package Registry"',
                '\'upload_failed=0; uploaded=0; for artifact in build/libs/*.jar target/*.jar target/*.war dist/*.zip dist/*.tgz; do [ -f "$artifact" ] || continue; file_name="$(basename "$artifact")"; if curl --fail --header "JOB-TOKEN: ${CI_JOB_TOKEN}" --upload-file "$artifact" "${CI_API_V4_URL}/projects/${CI_PROJECT_ID}/packages/generic/${CI_PROJECT_NAME}/${CI_PIPELINE_IID}/${file_name}"; then uploaded=1; else upload_failed=1; fi; done; if [ "$uploaded" = "0" ]; then echo "No package was uploaded; GitLab package upload may be unavailable in this environment"; fi; if [ "$upload_failed" = "1" ]; then echo "GitLab package upload returned an error; build artifact was still produced successfully"; fi\'',
            ]
        elif artifact_target == "nexus":
            publish_script = [
                'echo "Nexus artifact publishing selected"',
                'echo "Configure project-specific Nexus coordinates before enabling upload"',
                'find . -maxdepth 4 -type f \\( -name "*.jar" -o -name "*.war" -o -name "*.zip" -o -name "*.tgz" -o -name "*.whl" \\) || true',
            ]

        def _yaml_list(items: List[str], indent: str = "    - ") -> str:
            return "\n".join(f"{indent}{item}" for item in items)

        compile_artifacts = ""
        publish_artifacts = ""
        report_artifacts = ""
        security_artifacts = ""
        if use_gitlab_artifacts:
            compile_artifacts = f"""
  artifacts:
    when: always
    expire_in: 7 days
    paths:
{_yaml_list(artifact_paths, "      - ")}
"""
            publish_artifacts = f"""
  artifacts:
    when: always
    expire_in: 30 days
    paths:
{_yaml_list(artifact_paths, "      - ")}
"""
            report_artifacts = """
  artifacts:
    when: always
    paths:
      - semgrep-report.json
"""
            security_artifacts = """
  artifacts:
    when: always
    paths:
      - trivy-fs-report.json
"""

        return f"""stages:
  - compile
  - test
  - sast
  - quality
  - security
  - publish
  - notify
  - learn

variables:
  NEXUS_REGISTRY: "localhost:5001"
  NEXUS_PULL_REGISTRY: "localhost:5001"
  NEXUS_INTERNAL_REGISTRY: "ai-nexus:5001"
  IMAGE_NAME: "${{CI_PROJECT_NAME}}"
  IMAGE_TAG: "artifact-${{CI_PIPELINE_IID}}"
  SONARQUBE_URL: "http://ai-sonarqube:9000"
  SPLUNK_HEC_URL: "http://ai-splunk:8088"
  DEVOPS_BACKEND_URL: "http://devops-tools-backend:8003"

compile:
  stage: compile
  image: {image_ref}
  tags: [docker]
  script:
{_yaml_list(compile_script)}{compile_artifacts}

test:
  stage: test
  image: {image_ref}
  tags: [docker]
  needs: ["compile"]
  script:
{_yaml_list(test_script)}

sast:
  stage: sast
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/alpine-curl:latest
  tags: [docker]
  script:
    - echo "SAST placeholder for direct artifact pipeline" > semgrep-report.json{report_artifacts}

quality:
  stage: quality
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/sonarsource-sonar-scanner-cli:latest
  tags: [docker]
  script:
    - sonar-scanner -Dsonar.projectKey=${{CI_PROJECT_NAME}} -Dsonar.sources=. -Dsonar.host.url=${{SONARQUBE_URL}} -Dsonar.login=${{SONAR_TOKEN}} || true

security_scan:
  stage: security
  image:
    name: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/aquasec-trivy:latest
    entrypoint: [""]
  tags: [docker]
  script:
    - trivy fs --format json --output trivy-fs-report.json . || true{security_artifacts}

publish_artifact:
  stage: publish
  image: {image_ref}
  tags: [docker]
  needs: ["compile"]
  script:
{_yaml_list(publish_script)}{publish_artifacts}

notify_success:
  stage: notify
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/curlimages-curl:latest
  tags: [docker]
  when: on_success
  script:
    - 'curl -k -X POST "${{SPLUNK_HEC_URL}}/services/collector" -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" -d "{{\\"event\\": \\"Direct artifact pipeline succeeded\\", \\"source\\": \\"${{CI_PROJECT_NAME}}\\"}}" || true'

notify_failure:
  stage: notify
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/curlimages-curl:latest
  tags: [docker]
  when: on_failure
  script:
    - 'curl -k -X POST "${{SPLUNK_HEC_URL}}/services/collector" -H "Authorization: Splunk ${{SPLUNK_HEC_TOKEN}}" -d "{{\\"event\\": \\"Direct artifact pipeline failed\\", \\"source\\": \\"${{CI_PROJECT_NAME}}\\"}}" || true'

learn_record:
  stage: learn
  image: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/curlimages-curl:latest
  tags: [docker]
  when: always
  allow_failure: true
  script:
    - 'curl -X POST "${{DEVOPS_BACKEND_URL}}/api/v1/pipeline/learn/record" -H "Content-Type: application/json" -d "{{\\"repo_url\\":\\"${{CI_PROJECT_URL}}\\",\\"branch\\":\\"${{CI_COMMIT_REF_NAME}}\\",\\"pipeline_id\\":${{CI_PIPELINE_ID}},\\"gitlab_token\\":\\"${{GITLAB_TOKEN}}\\"}}" || true'
"""

    def _get_direct_artifact_commands(
        self,
        analysis: Dict[str, Any],
    ) -> Tuple[List[str], List[str], List[str]]:
        language = str(analysis.get("language", "unknown")).lower()
        build_tool = str(
            analysis.get("build_tool") or analysis.get("package_manager") or ""
        ).lower()
        packaging = str(analysis.get("packaging") or "jar").lower()

        if language in ("java", "kotlin", "scala"):
            artifact_pattern = analysis.get("artifact_pattern")
            if not artifact_pattern:
                artifact_pattern = "target/*.war" if packaging == "war" else "build/libs/*.jar"
                if build_tool == "maven":
                    artifact_pattern = "target/*.war" if packaging == "war" else "target/*.jar"
            if build_tool == "gradle":
                return (
                    [
                        "if [ -x ./gradlew ]; then ./gradlew clean assemble -x test; else gradle clean assemble -x test; fi"
                    ],
                    [
                        "if [ -x ./gradlew ]; then ./gradlew test; else gradle test; fi"
                    ],
                    [artifact_pattern],
                )
            return (
                ["if [ -x ./mvnw ]; then ./mvnw -B clean package -DskipTests; else mvn -B clean package -DskipTests; fi"],
                ["if [ -x ./mvnw ]; then ./mvnw -B test; else mvn -B test; fi"],
                [artifact_pattern],
            )

        if language in ("javascript", "typescript"):
            package_manager = "yarn" if build_tool == "yarn" else "npm"
            install_cmd = "yarn install --frozen-lockfile" if package_manager == "yarn" else "npm ci || npm install"
            build_cmd = "yarn build || true" if package_manager == "yarn" else "npm run build || true"
            test_cmd = "yarn test --watch=false || true" if package_manager == "yarn" else "npm test -- --watch=false || true"
            return ([install_cmd, build_cmd], [test_cmd], ["dist/", "build/"])

        if language == "python":
            return (
                ["python -m pip install --upgrade pip", "pip install -r requirements.txt || true", "python -m build || true"],
                ["pytest || true"],
                ["dist/"],
            )

        if language in ("go", "golang"):
            return (
                ["go mod download", "go build -o app ./..."],
                ["go test ./..."],
                ["app"],
            )

        return (
            ['echo "No compile command detected; add project-specific build command here"'],
            ['echo "No test command detected; add project-specific test command here"'],
            ["dist/", "build/", "target/"],
        )

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

    async def get_reference_pipeline(
        self,
        language: str,
        framework: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        from .templates import get_reference_pipeline
        return await get_reference_pipeline(language, framework, analysis=analysis)

    async def get_best_pipeline_config(
        self,
        language: str,
        framework: str = "",
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        from .templates import get_best_pipeline_config
        return await get_best_pipeline_config(language, framework, analysis=analysis)

    async def get_best_template_files(
        self,
        language: str,
        framework: str = "",
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, str]]:
        from .templates import get_best_template_files
        return await get_best_template_files(language, framework, analysis=analysis)

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
        use_template_only: bool = False,
        progress_key: Optional[str] = None,
        force_llm: bool = False,
        pipeline_requirements: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """
        Generate .gitlab-ci.yml and Dockerfile using the active LLM provider with RL feedback.
        Uses the pipeline-generator-v2 model with 8-stage pipeline knowledge.

        If use_template_only=True, skips LLM and returns default templates directly.
        """
        # Use default model if not specified
        if model is None:
            model = self.DEFAULT_MODEL

        # Live phase updates for the chatbot UI — guarded import so we
        # don't blow up when this generator is invoked outside of a chat
        # context (the helpers no-op when progress_key is None/empty).
        from app.services.chat_inflight import set_phase as _phase

        _phase(progress_key, "analyzing", "Analyzing repository (language, framework, files)...")
        # Analyze repository
        analysis = await self.analyze_repository(repo_url, gitlab_token)
        self._apply_pipeline_requirements(analysis, pipeline_requirements)
        if pipeline_requirements:
            _phase(
                progress_key,
                "requirements_confirmed",
                "Using chat-confirmed pipeline requirements.",
                language=analysis.get("language"),
                framework=analysis.get("framework"),
            )

        if self._is_direct_artifact_mode(analysis):
            print(f"[Direct Artifact] Generating artifact-only pipeline for {analysis.get('language')}")
            _phase(
                progress_key,
                "direct_artifact",
                "Direct artifact mode selected; generating pipeline without a Dockerfile.",
                language=analysis.get("language"),
                framework=analysis.get("framework"),
            )
            gitlab_ci = self._get_direct_artifact_gitlab_ci(analysis)
            source_label = _format_source_label(
                "direct-artifact-template",
                has_rag_reference=False,
            )
            gitlab_ci = _stamp_pipeline_source(
                gitlab_ci,
                source_label,
                "direct-artifact-template",
            )
            try:
                from .image_seeder import ensure_images_in_nexus
                await ensure_images_in_nexus(gitlab_ci)
            except Exception as e:
                print(f"[ImageSeeder] Direct artifact seed warning: {e}")
            return {
                "gitlab_ci": gitlab_ci,
                "dockerfile": "",
                "analysis": analysis,
                "model_used": "direct-artifact-template",
                "feedback_used": 0,
                "template_source": source_label,
                "source_token": "direct-artifact-template",
                "rag_hit": False,
                "had_rag_reference": False,
                "fix_attempts": 0,
                "validation_passed": True,
                "persisted_to_rag": False,
                "final_errors": [],
            }

        if force_llm:
            _phase(
                progress_key, "checking_rag",
                f"Skipping direct RAG reuse for forced LLM self-heal test ({analysis.get('language','?')}/{analysis.get('framework','?')}).",
                language=analysis.get('language'),
                framework=analysis.get('framework'),
            )
        else:
            _phase(
                progress_key, "checking_rag",
                f"Checking RAG cache for proven {analysis.get('language','?')}/{analysis.get('framework','?')} template...",
                language=analysis.get('language'),
                framework=analysis.get('framework'),
            )

        # If use_template_only, skip LLM and return default templates directly
        if use_template_only:
            print(f"[Template Mode] Returning default templates for {analysis['language']}")
            gitlab_ci = self._get_default_gitlab_ci(analysis)
            # Ensure learn stage is present for RL
            gitlab_ci = self._ensure_learn_stage(gitlab_ci)
            dockerfile = self._get_default_dockerfile(analysis)
            source_label = _format_source_label("template-only", has_rag_reference=False)
            gitlab_ci = _stamp_pipeline_source(gitlab_ci, source_label, "default-template")
            return {
                'gitlab_ci': gitlab_ci,
                'dockerfile': dockerfile,
                'analysis': analysis,
                'model_used': 'template-only',
                'template_source': source_label,
                'feedback_used': 0,
                'source_token': 'template-only',
                'rag_hit': False,
                'fix_attempts': 0,
                'validation_passed': False,  # not validated, default fallback
                'persisted_to_rag': False,
            }

        # ===================================================================
        # PRIORITY 1: Check ChromaDB for PROVEN templates
        # - Ollama: Use template DIRECTLY without LLM (Ollama tends to ignore templates)
            # - CLI providers: pass template as mandatory reference for adaptation
        # ===================================================================
        template_files = None
        if force_llm:
            print(
                f"[LLM-Forced] Skipping direct ChromaDB template for "
                f"{analysis['language']}/{analysis['framework']}."
            )
        else:
            print(f"[RL-Direct] Checking for proven templates for {analysis['language']}/{analysis['framework']}...")
            template_files = await self.get_best_template_files(
                analysis['language'],
                analysis['framework'],
                analysis=analysis,
            )

        if template_files and template_files.get('gitlab_ci'):
            has_dockerfile = bool(template_files.get('dockerfile'))

            # Use proven template DIRECTLY when:
            # - It's an exact language match (not cross-language)
            # - It has both .gitlab-ci.yml AND Dockerfile
            # This avoids LLM re-generation which can introduce regressions.
            if has_dockerfile:
                print("[RL-Direct] Found proven template with Dockerfile! Using DIRECTLY (no LLM).")
                _phase(
                    progress_key, "rag_hit",
                    f"Template found in RAG ({analysis.get('language')}/{analysis.get('framework')}). No LLM call.",
                    rag_hit=True,
                    language=analysis.get('language'),
                    framework=analysis.get('framework'),
                )
                gitlab_ci = template_files['gitlab_ci']
                dockerfile = template_files['dockerfile']
                gitlab_ci = self._validate_and_fix_pipeline(gitlab_ci, None)
                gitlab_ci = self._ensure_learn_stage(gitlab_ci)
                gitlab_ci = _disable_learn_recording_for_rag_hit(gitlab_ci)

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

                source_label = _format_source_label("chromadb-direct", has_rag_reference=True)
                gitlab_ci = _stamp_pipeline_source(gitlab_ci, source_label, "chromadb-direct")
                return {
                    'gitlab_ci': gitlab_ci,
                    'dockerfile': dockerfile,
                    'analysis': analysis,
                    'model_used': 'chromadb-direct',
                    'feedback_used': 0,
                    'template_source': source_label,
                    'source_token': 'chromadb-direct',
                    'rag_hit': True,
                    'fix_attempts': 0,
                    'validation_passed': True,
                    'persisted_to_rag': True,  # already in RAG by definition
                }
            else:
                # Template has .gitlab-ci.yml but no Dockerfile — pass to LLM as reference
                print("[RL+LLM] Found proven template (no Dockerfile). Passing to LLM as reference.")
        else:
            template_files = None

        if not template_files:
            print("[RL-Direct] No proven template found in ChromaDB...")

        # ===================================================================
        # PRIORITY 2: Use LLM to generate (CLI providers adapt RAG templates, Ollama from scratch)
        # ===================================================================
        language = analysis.get('language', 'unknown').lower()

        # If a CLI provider has a proven template from Priority 1, use it as the reference.
        ref_source_language = language  # Track which language the reference came from
        if template_files and template_files.get('gitlab_ci'):
            reference_pipeline = template_files['gitlab_ci']
            print(f"[RL+LLM] Passing proven RAG template as reference to LLM for {language}...")
        else:
            print(f"[LLM-Generate] No RAG template for {language}. LLM is creating a new pipeline...")
            # Fallback: query ChromaDB for a reference pipeline (may be cross-language)
            reference_pipeline, ref_source_language = await self.get_reference_pipeline(
                analysis['language'],
                analysis['framework'],
                analysis=analysis,
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
- For registry API checks from CI jobs, use http://${{NEXUS_INTERNAL_REGISTRY}}/v2/
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
    - 'printf ''{{"auths":{{"%s":{{"username":"%s","password":"%s"}}}}}}'' "$NEXUS_INTERNAL_REGISTRY" "$NEXUS_USERNAME" "$NEXUS_PASSWORD" > /kaniko/.docker/config.json'
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
- ai-nexus:5001/apm-repo/demo/hexpm-elixir:1.16.3-erlang-26.2.5-alpine-3.19.1 (Elixir/Phoenix)
- ai-nexus:5001/apm-repo/demo/alpine:3.18 (Alpine base)
- ai-nexus:5001/apm-repo/demo/nginx:alpine (Nginx)

### ELIXIR/PHOENIX RULE
- If mix.exs is present, use hexpm-elixir:1.16.3-erlang-26.2.5-alpine-3.19.1.
- Never install Elixir or Erlang using apk inside Alpine jobs.
- Compile with mix local.hex, mix local.rebar, mix deps.get --only ${{MIX_ENV}}, mix deps.compile, mix compile.
- Build Docker releases with mix release and run them from alpine:3.18.

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

        # Surface to the chatbot UI: we're now actively calling the LLM.
        # Show different copy depending on whether we have a RAG reference
        # (LLM is "adapting" a known-good template) vs raw generation.
        if had_rag_reference if False else True:  # always true to compute message; vars below
            pass
        _llm_msg_suffix = (
            f" (adapting {ref_source_language} template)"
            if reference_pipeline and ref_source_language and ref_source_language.lower() != language.lower()
            else (" (using RAG reference)" if reference_pipeline else " (no RAG match — generating from scratch)")
        )
        _phase(
            progress_key, "calling_llm",
            f"Calling {get_active_provider_name()} to generate pipeline{_llm_msg_suffix}. This typically takes 15-60s...",
            language=analysis.get('language'),
            framework=analysis.get('framework'),
        )

        # Call LLM to generate with strict settings
        llm = self._get_llm()
        try:
            response = await llm.generate(
                model=model,
                prompt=prompt,
                options={
                    "temperature": 0.1,  # Very low for deterministic output
                    "num_predict": 12000,  # Bumped from 6000: 9-stage pipelines truncated mid-line
                    "top_p": 0.9,
                    "repeat_penalty": 1.1
                }
            )

            # FIX: Handle None response from LLM
            if response is None:
                fallback_yml = self._get_default_gitlab_ci(analysis)
                fallback_yml = self._ensure_learn_stage(fallback_yml)
                fallback_label = _format_source_label("default-template", has_rag_reference=False)
                fallback_yml = _stamp_pipeline_source(fallback_yml, fallback_label, "default-template")
                return {
                    "gitlab_ci": fallback_yml,
                    "dockerfile": self._get_default_dockerfile(analysis),
                    "analysis": analysis,
                    "model_used": get_active_provider_name(),
                    "template_source": fallback_label,
                    "feedback_used": len(feedback),
                    "error": "LLM returned empty response",
                    "source_token": "default-template",
                    "rag_hit": False,
                    "fix_attempts": 0,
                    "validation_passed": False,
                    "persisted_to_rag": False,
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

            # ===================================================================
            # POST-LLM: Run the dry-run validator + iterative LLM fixer
            # (max 10 attempts). On success, persist back to RAG so the next
            # request for this language/framework hits Priority-1 RAG instead.
            # ===================================================================
            had_rag_reference = bool(template_files) or bool(reference_pipeline)
            had_extraction_failure = not gitlab_ci
            fix_attempts = 1
            validation_passed = False
            persisted_to_rag = False
            persist_action: Optional[str] = None
            persist_error: Optional[str] = None
            final_errors: List[str] = []

            if not had_extraction_failure:
                try:
                    project_path = (
                        self.parse_gitlab_url(repo_url).get('path') if repo_url else None
                    )
                except Exception:
                    project_path = None

                print(
                    f"[Fixer-Loop] Running dry-run validator + LLM fixer "
                    f"(max 10 attempts) for {analysis['language']}/{analysis['framework']}..."
                )
                _phase(
                    progress_key, "fixer_starting",
                    "Running dry-run validator + LLM fixer (max 10 attempts)...",
                )
                try:
                    fix_result = await gitlab_llm_fixer.iterative_fix(
                        gitlab_ci=final_gitlab_ci,
                        dockerfile=final_dockerfile,
                        validator=gitlab_dry_run_validator,
                        analysis=analysis,
                        gitlab_token=gitlab_token,
                        project_path=project_path,
                        max_attempts=10,
                        model=model,
                        progress_key=progress_key,
                    )
                    fix_attempts = fix_result.get('attempts', 1)
                    validation_passed = bool(fix_result.get('success'))
                    final_errors = fix_result.get('final_errors', []) or []

                    if validation_passed:
                        # Adopt the fixer's outputs (may have been corrected)
                        final_gitlab_ci = fix_result.get('gitlab_ci') or final_gitlab_ci
                        final_dockerfile = fix_result.get('dockerfile') or final_dockerfile
                        # Re-validate images & re-seed in case the fixer rewrote them
                        final_gitlab_ci, final_dockerfile, _ = self.validate_and_fix_pipeline_images(
                            final_gitlab_ci, final_dockerfile, analysis['language']
                        )
                        # NOTE: We deliberately DO NOT persist to RAG here.
                        # RAG persistence happens only after the pipeline
                        # actually succeeds in GitLab — driven by the
                        # `learn_record` job in the generated YAML, which
                        # POSTs to /api/v1/pipeline/learn/record →
                        # `record_pipeline_result` → `store_successful_pipeline`.
                        # Dry-run validation passing is necessary but NOT
                        # sufficient evidence that a template should be cached.
                        print(
                            f"[Fixer-Loop] VALID after {fix_attempts} attempt(s); "
                            f"awaiting GitLab pipeline run for RAG persistence."
                        )
                    else:
                        # Fixer exhausted all attempts. Surface a hard
                        # failure to the caller so the chat tool can refuse
                        # to commit a broken pipeline.
                        print(
                            f"[Fixer-Loop] FAILED after {fix_attempts} attempt(s). "
                            f"Final errors: {final_errors[:5]}"
                        )
                except Exception as fix_err:
                    print(f"[Fixer-Loop] Exception during iterative_fix: {fix_err}")
                    fix_attempts = 1
                    validation_passed = False

            # Decide which source label fits this generation.
            used_generic_reference = bool(reference_pipeline) and str(ref_source_language).lower() == "generic"
            if had_extraction_failure:
                source_token = "default-template"
            elif used_generic_reference:
                source_token = "generic-template-llm-fixed" if fix_attempts > 1 else "generic-template-llm"
            elif is_cross_language and had_rag_reference:
                source_token = "cross-language-rag-fixed" if fix_attempts > 1 else "cross-language-rag"
            elif had_rag_reference:
                source_token = "rag-llm-adapt-fixed" if fix_attempts > 1 else "rag-llm-adapt"
            else:
                source_token = "llm-fixer-loop" if fix_attempts > 1 else "llm-generate"

            generator_name = get_active_provider_name()
            source_label = _format_source_label(source_token, has_rag_reference=had_rag_reference)
            final_gitlab_ci = _stamp_pipeline_source(
                final_gitlab_ci, source_label, generator_name
            )

            return {
                "gitlab_ci": final_gitlab_ci,
                "dockerfile": final_dockerfile,
                "analysis": analysis,
                "model_used": generator_name,
                "template_source": source_label,
                "feedback_used": len(feedback),
                "source_token": source_token,
                "rag_hit": False,  # if we got here, RAG-direct didn't fire
                "had_rag_reference": had_rag_reference,
                "fix_attempts": fix_attempts,
                "validation_passed": validation_passed,
                "persisted_to_rag": persisted_to_rag,
                "persist_action": persist_action,
                "final_errors": final_errors[:10] if final_errors else [],
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
            model: Model hint for the active LLM provider
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
                'model_used': get_active_provider_name(),
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
                'model_used': get_active_provider_name(),
                'feedback_used': result.get('feedback_used', 0),
                'validation_passed': False,
                'validation_errors': fix_result.get('final_errors', all_errors),
                'fix_attempts': fix_result.get('attempts', max_fix_attempts),
                'fix_history': fix_result.get('fix_history', [])
            }
