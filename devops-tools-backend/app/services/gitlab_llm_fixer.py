"""
GitLab Pipeline LLM Fixer

Uses the configured LLM provider to fix GitLab CI/CD pipeline errors.

Two distinct fix flows are supported:

1. ``iterative_fix(...)``  — pre-commit, validation-driven loop. Calls the
   ``GitLabDryRunValidator`` (YAML lint, structure check, GitLab CI Lint API)
   to discover errors, asks the LLM to fix them, and repeats until clean or
   ``max_attempts`` is exhausted. Used by ``generate_with_validation`` before
   any commit reaches GitLab.

2. ``generate_fix(...)`` / ``fix_from_run_log(...)`` — post-failure, log-driven
   single-shot. Pulls the actual job trace from a failed GitLab pipeline,
   extracts the relevant error lines, classifies the error type, and asks
   the LLM to produce a fixed ``.gitlab-ci.yml`` + ``Dockerfile`` pair. Used
   by the self-healing background monitor (``monitor_pipeline_with_self_heal``)
   after a real GitLab failure has happened.

The two flows mirror the GitHub Actions self-healing implementation in
``app/services/github_llm_fixer.py``.
"""
import re
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple, List

import httpx
import yaml

from app.config import settings, tools_manager
from app.integrations.ollama import OllamaIntegration
from app.integrations.llm_provider import get_llm_provider, get_active_provider_name


# ---------------------------------------------------------------------------
# Output-quality helpers
# ---------------------------------------------------------------------------
# The LLM occasionally truncates its response mid-line when it bumps against
# its token budget. The truncation produces an unclosed quoted string in the
# YAML which GitLab silently accepts as "valid pipeline with 0 jobs" — that
# burns a self-heal attempt for no progress. Detect and reject such output.

def _is_truncated_yaml(text: Optional[str]) -> Tuple[bool, str]:
    """Return (truncated, reason). Empty/None counts as truncated."""
    if not text or not text.strip():
        return True, "empty"
    # Last non-blank line should not end mid-quote / mid-pair / mid-flow.
    last = next((ln for ln in reversed(text.splitlines()) if ln.strip()), "")
    # Odd number of unescaped double quotes on the last line is a strong signal
    # that the model ran out of tokens partway through a quoted scalar.
    unescaped_dq = len(re.findall(r'(?<!\\)"', last))
    if unescaped_dq % 2 == 1:
        return True, f"odd dquote count on last line: {last[-80:]!r}"
    # Trailing line that ends with an open bracket / continuation
    if last.rstrip().endswith(("{", "[", ",", ":", "-d", "\\")):
        return True, f"last line ends with open token: {last[-60:]!r}"
    # Final hard check: must parse as YAML.
    try:
        yaml.safe_load(text)
    except yaml.YAMLError as e:
        return True, f"yaml parse error: {str(e)[:200]}"
    return False, ""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class FixResult:
    """Structured outcome of a single LLM fix attempt.

    Mirrors ``app.services.github_llm_fixer.FixResult`` so the GitLab and
    GitHub self-healing flows share the same downstream consumer shape.
    """
    success: bool
    gitlab_ci: Optional[str]
    dockerfile: Optional[str]
    explanation: str
    error_type: str
    changes_made: list


class GitLabLLMFixer:
    """
    Uses LLM to fix GitLab CI/CD pipeline errors.

    Flow (validation-driven, used pre-commit):
    1. Receives pipeline YAML with validation errors
    2. Constructs prompt with errors and best practices
    3. Gets LLM to fix the issues
    4. Returns corrected pipeline

    Flow (log-driven, used by self-healing monitor post-commit):
    1. Receives the live trace log from a failed GitLab job
    2. Classifies the error type and extracts the relevant lines
    3. Calls the LLM with explicit Nexus-only / 8-stage / docker-tags rules
    4. Returns a ``FixResult`` with new gitlab_ci + dockerfile
    """

    FIX_MODEL = "pipeline-generator-v5"  # Same model used for generation

    # Common error patterns and their canonical error_type label.
    # Order matters — first match wins. Keep specific patterns above generic.
    ERROR_PATTERNS = [
        (r'manifest unknown|image not found|pull access denied|name unknown|repository does not exist', 'image_not_found'),
        (r'connection refused|ECONNREFUSED|no route to host|could not resolve host', 'service_connection'),
        (r'command not found|: not found$|executable file not found', 'missing_command'),
        (r'permission denied|EACCES|operation not permitted', 'permission_error'),
        (r'timeout|timed out|context deadline exceeded', 'timeout_error'),
        (r'yaml.*error|syntax error|parse error|invalid yaml', 'yaml_syntax'),
        (r'authentication.*failed|401 unauthorized|403 forbidden|access denied', 'auth_error'),
        (r'out of memory|OOM|killed|cannot allocate memory', 'resource_error'),
        (r'maven|mvn .* error|java.* exception', 'java_build'),
        (r'pip install|requirement|module not found', 'python_build'),
        (r'go build|cannot find package|undefined:', 'go_build'),
        (r'cargo build|rustc|error\[E\d+\]', 'rust_build'),
        (r'npm err|yarn err|node.*error', 'node_build'),
        (r'kaniko|build failed|dockerfile', 'build_failure'),
        (r'error|failed|exception|fatal', 'generic_error'),
    ]

    def __init__(self):
        self.ollama_config = tools_manager.get_tool("ollama")
        self.gitlab_url = settings.gitlab_url

    def _get_llm(self):
        """Get the configured LLM provider."""
        return get_llm_provider()

    # ------------------------------------------------------------------
    # Helpers shared by both fix flows
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Strip leading/trailing markdown ``` fences from extracted content."""
        if not text:
            return text
        text = re.sub(r'^```\w*\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
        return text.strip()

    def identify_error_type(self, error_log: str) -> str:
        """Classify a job error log to one of the known error_type labels.

        Returns ``'unknown_error'`` if no pattern matches.
        """
        if not error_log:
            return 'unknown_error'
        log_lower = error_log.lower()
        for pattern, error_type in self.ERROR_PATTERNS:
            if re.search(pattern, log_lower):
                return error_type
        return 'unknown_error'

    def extract_key_errors(self, error_log: str, max_lines: int = 50) -> str:
        """Extract the most relevant error lines from a job trace.

        We first scan for lines containing keywords (``error``, ``failed``,
        ``exception``, etc.). If nothing matches we fall back to the trailing
        ``max_lines`` of the log so the LLM still has context.
        """
        if not error_log:
            return ''
        lines = error_log.splitlines()
        keywords = (
            'error', 'failed', 'exception', 'fatal',
            'cannot', 'unable', 'not found', 'denied',
            'reject', 'panic', 'traceback', 'undefined'
        )
        hits: List[str] = []
        for line in lines:
            ll = line.lower()
            if any(k in ll for k in keywords):
                stripped = line.strip()
                if stripped:
                    hits.append(stripped)
        if not hits:
            hits = [l.strip() for l in lines[-max_lines:] if l.strip()]
        return '\n'.join(hits[:max_lines])

    # ------------------------------------------------------------------
    # Existing flow: validation-driven LLM fix (kept for iterative_fix)
    # ------------------------------------------------------------------

    async def fix_pipeline(
        self,
        gitlab_ci: str,
        dockerfile: str,
        errors: list,
        warnings: list,
        analysis: Dict[str, Any],
        model: str = None
    ) -> Dict[str, str]:
        """
        Fix pipeline using LLM based on validation errors.

        Args:
            gitlab_ci: Current pipeline YAML with errors
            dockerfile: Current Dockerfile
            errors: List of validation errors
            warnings: List of validation warnings
            analysis: Repository analysis result
            model: Ollama model to use

        Returns:
            Dict with fixed gitlab_ci and dockerfile
        """
        model = model or self.FIX_MODEL

        # Build error context
        error_context = ""
        if errors:
            error_context = "## CRITICAL ERRORS TO FIX:\n"
            for i, err in enumerate(errors, 1):
                error_context += f"{i}. {err}\n"

        warning_context = ""
        if warnings:
            warning_context = "\n## WARNINGS TO ADDRESS:\n"
            for i, warn in enumerate(warnings, 1):
                warning_context += f"{i}. {warn}\n"

        prompt = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    GITLAB PIPELINE FIX REQUEST                                ║
╚══════════════════════════════════════════════════════════════════════════════╝

You must fix the following GitLab CI/CD pipeline that has validation errors.

## PROJECT INFO:
- Language: {analysis.get('language', 'unknown')}
- Framework: {analysis.get('framework', 'generic')}
- Package Manager: {analysis.get('package_manager', 'unknown')}

{error_context}
{warning_context}

## CURRENT PIPELINE (WITH ERRORS):
```yaml
{gitlab_ci}
```

## CURRENT DOCKERFILE:
```dockerfile
{dockerfile}
```

## MANDATORY RULES FOR FIX:
1. ALL images MUST use Nexus registry: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/<image>:<tag>
2. ALL Dockerfile FROM statements MUST use: ${{BASE_REGISTRY}}/apm-repo/demo/<image>:<tag>
3. Pipeline MUST have exactly 8 stages: compile, build, test, sast, quality, security, push, notify
4. ALL jobs MUST have: tags: [docker]
5. Kaniko build job MUST use ${{NEXUS_INTERNAL_REGISTRY}} for push destination
6. YAML syntax must be valid

## AVAILABLE NEXUS IMAGES:
- amazoncorretto:17-alpine-jdk (Java runtime)
- maven:3.9-eclipse-temurin-17 (Maven/Java build - use for Scala too)
- python:3.11-slim (Python)
- node:18-alpine (Node.js)
- golang:1.21-alpine (Go)
- perl:5.32-slim (Perl)
- hexpm-elixir:1.16.3-erlang-26.2.5-alpine-3.19.1 (Elixir/Phoenix)
- alpine:3.18 (Alpine base)
- nginx:alpine (Nginx)
- kaniko-executor:debug (Kaniko)
- aquasec-trivy:latest (Trivy)
- curlimages-curl:latest (Curl)
- sonarsource-sonar-scanner-cli:5 (SonarQube)

## LANGUAGE-SPECIFIC NOTES:
- Scala: No SBT image exists! Use maven:3.9-eclipse-temurin-17 and install SBT:
  script:
    - curl -fL "https://github.com/sbt/sbt/releases/download/v1.9.8/sbt-1.9.8.tgz" | tar xz -C /tmp
    - export PATH="/tmp/sbt/bin:$PATH"
    - sbt clean compile package
- Perl: Use perl:5.32-slim. Build/test commands:
    - '[ -f Makefile.PL ] && perl Makefile.PL && make || echo "no Makefile.PL"'
    - 'prove -lv t/ 2>/dev/null || echo "no tests"'
- Elixir/Phoenix: Use hexpm-elixir:1.16.3-erlang-26.2.5-alpine-3.19.1.
  Never install Elixir or Erlang with apk. Verify pushed images from CI jobs
  with http://${{NEXUS_INTERNAL_REGISTRY}}, not localhost.

## RESPONSE FORMAT:
Return ONLY the fixed files in this exact format:

=== .gitlab-ci.yml ===
<fixed gitlab-ci.yml content here>

=== Dockerfile ===
<fixed Dockerfile content here>

Do NOT include any explanations - just the fixed files.
"""

        llm = self._get_llm()

        try:
            response = await llm.generate(
                prompt=prompt,
                model=model
            )

            response_text = response.get('response', '')

            # Parse the response to extract fixed files
            gitlab_ci_fixed, dockerfile_fixed = self._parse_fix_response(
                response_text, gitlab_ci, dockerfile
            )

            return {
                'gitlab_ci': gitlab_ci_fixed,
                'dockerfile': dockerfile_fixed,
                'raw_response': response_text
            }

        except Exception as e:
            print(f"[LLM Fixer] Error fixing pipeline: {e}")
            # Return original files if fix fails
            return {
                'gitlab_ci': gitlab_ci,
                'dockerfile': dockerfile,
                'error': str(e)
            }
        finally:
            await llm.close()

    def _parse_fix_response(
        self,
        response: str,
        original_gitlab_ci: str,
        original_dockerfile: str
    ) -> Tuple[str, str]:
        """Parse the LLM response to extract fixed files.

        Tolerates several formats: ``=== .gitlab-ci.yml ===`` markers,
        ```` ```yaml ```` fenced blocks, or plain ``.gitlab-ci.yml:`` headers.
        """
        gitlab_ci = original_gitlab_ci
        dockerfile = original_dockerfile

        # Try to find gitlab-ci.yml section
        gitlab_patterns = [
            r'===\s*\.gitlab-ci\.yml\s*===\s*(.*?)(?:===\s*Dockerfile|$)',
            r'```yaml\s*(.*?)```',
            r'\.gitlab-ci\.yml:?\s*\n(.*?)(?:Dockerfile:|$)'
        ]

        for pattern in gitlab_patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                # Clean up markdown code blocks
                content = re.sub(r'^```\w*\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                if content and 'stages:' in content:
                    gitlab_ci = content
                    break

        # Try to find Dockerfile section
        dockerfile_patterns = [
            r'===\s*Dockerfile\s*===\s*(.*?)(?:===|$)',
            r'```dockerfile\s*(.*?)```',
            r'Dockerfile:?\s*\n(.*?)$'
        ]

        for pattern in dockerfile_patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                # Clean up markdown code blocks
                content = re.sub(r'^```\w*\s*', '', content)
                content = re.sub(r'\s*```$', '', content)
                if content and ('FROM' in content.upper() or 'ARG' in content.upper()):
                    dockerfile = content
                    break

        return gitlab_ci, dockerfile

    async def iterative_fix(
        self,
        gitlab_ci: str,
        dockerfile: str,
        validator,
        analysis: Dict[str, Any],
        gitlab_token: str,
        project_path: str = None,
        max_attempts: int = 10,
        model: str = None,
        progress_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Iteratively fix pipeline until validation passes or max attempts reached.

        Args:
            gitlab_ci: Initial pipeline YAML
            dockerfile: Initial Dockerfile
            validator: GitLabDryRunValidator instance
            analysis: Repository analysis
            gitlab_token: GitLab API token
            project_path: Project path for GitLab lint API
            max_attempts: Maximum fix attempts
            model: Ollama model to use

        Returns:
            Dict with final files and fix history
        """
        # Live phase publisher — no-ops when progress_key is None.
        from app.services.chat_inflight import set_phase as _phase

        current_gitlab_ci = gitlab_ci
        current_dockerfile = dockerfile
        fix_history = []

        for attempt in range(1, max_attempts + 1):
            print(f"[LLM Fixer] Attempt {attempt}/{max_attempts}")
            _phase(
                progress_key, "fixer_attempt",
                f"LLM fixer attempt {attempt}/{max_attempts} — validating pipeline...",
                fix_attempts=attempt, max_attempts=max_attempts,
            )

            # Validate current state
            results = await validator.validate_all(
                current_gitlab_ci,
                current_dockerfile,
                gitlab_token,
                project_path
            )

            all_valid, summary = validator.get_validation_summary(results)

            # Collect errors and warnings
            all_errors = []
            all_warnings = []
            for check_name, result in results.items():
                all_errors.extend([f"[{check_name}] {e}" for e in result.errors])
                all_warnings.extend([f"[{check_name}] {w}" for w in result.warnings])

            fix_history.append({
                'attempt': attempt,
                'valid': all_valid,
                'errors': all_errors,
                'warnings': all_warnings
            })

            if all_valid:
                print(f"[LLM Fixer] Pipeline valid after {attempt} attempt(s)")
                return {
                    'success': True,
                    'gitlab_ci': current_gitlab_ci,
                    'dockerfile': current_dockerfile,
                    'attempts': attempt,
                    'fix_history': fix_history,
                    'fixer_model_used': get_active_provider_name()
                }

            # Only consider errors as blocking, not warnings
            if not all_errors:
                print(f"[LLM Fixer] No critical errors, only warnings - accepting pipeline")
                return {
                    'success': True,
                    'gitlab_ci': current_gitlab_ci,
                    'dockerfile': current_dockerfile,
                    'attempts': attempt,
                    'fix_history': fix_history,
                    'has_warnings': True,
                    'fixer_model_used': get_active_provider_name()
                }

            # Try to fix errors
            if attempt < max_attempts:
                print(f"[LLM Fixer] Fixing {len(all_errors)} errors...")
                _phase(
                    progress_key, "fixer_fixing",
                    f"Attempt {attempt}/{max_attempts}: LLM repairing {len(all_errors)} validation error(s)...",
                    fix_attempts=attempt, max_attempts=max_attempts,
                )
                fix_result = await self.fix_pipeline(
                    current_gitlab_ci,
                    current_dockerfile,
                    all_errors,
                    all_warnings,
                    analysis,
                    model
                )

                if 'error' not in fix_result:
                    current_gitlab_ci = fix_result['gitlab_ci']
                    current_dockerfile = fix_result['dockerfile']

        # Max attempts reached
        print(f"[LLM Fixer] Max attempts ({max_attempts}) reached")
        return {
            'success': False,
            'gitlab_ci': current_gitlab_ci,
            'dockerfile': current_dockerfile,
            'attempts': max_attempts,
            'fix_history': fix_history,
            'final_errors': all_errors,
            'fixer_model_used': get_active_provider_name()
        }

    # ------------------------------------------------------------------
    # New flow: log-driven, single-shot LLM fix (used by self-healing)
    # ------------------------------------------------------------------

    async def generate_fix(
        self,
        dockerfile: str,
        gitlab_ci: str,
        error_log: str,
        job_name: str,
        language: str,
        framework: str
    ) -> FixResult:
        """Generate a single-shot fix from a real GitLab job trace.

        Mirrors ``GitHubLLMFixer.generate_fix(...)``. Used by the
        ``monitor_pipeline_with_self_heal`` background task once a pipeline
        has actually failed in GitLab and we have the trace bytes in hand.
        """
        error_type = self.identify_error_type(error_log)
        key_errors = self.extract_key_errors(error_log)

        prompt = self._build_log_fix_prompt(
            dockerfile=dockerfile,
            gitlab_ci=gitlab_ci,
            key_errors=key_errors,
            job_name=job_name,
            language=language,
            framework=framework,
            error_type=error_type,
        )

        llm = self._get_llm()
        try:
            # num_predict 12000 (was 6000) — earlier value truncated mid-line
            # on full 9-stage pipelines, producing unclosed quoted strings that
            # GitLab parsed as "0-job pipeline" and burned self-heal attempts.
            response = await llm.generate(
                model=self.FIX_MODEL,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 12000,
                },
            )
            generated_text = (response or {}).get("response", "") or ""
            result = self._parse_log_fix_output(
                text=generated_text,
                error_type=error_type,
                original_gitlab_ci=gitlab_ci,
                original_dockerfile=dockerfile,
            )

            # Reject truncated output so the monitor can fall back to the
            # last-known-good RAG template instead of committing broken YAML.
            if result.gitlab_ci and result.gitlab_ci != gitlab_ci:
                truncated, reason = _is_truncated_yaml(result.gitlab_ci)
                if truncated:
                    return FixResult(
                        success=False,
                        gitlab_ci=None,
                        dockerfile=None,
                        explanation=(
                            f"LLM output appears truncated ({reason}). "
                            "Skipping commit so the monitor can fall back."
                        ),
                        error_type=error_type,
                        changes_made=[],
                    )
            return result
        except Exception as e:
            return FixResult(
                success=False,
                gitlab_ci=None,
                dockerfile=None,
                explanation=f"LLM fix generation failed: {e}",
                error_type=error_type,
                changes_made=[],
            )
        finally:
            try:
                await llm.close()
            except Exception:
                pass

    def _build_log_fix_prompt(
        self,
        dockerfile: str,
        gitlab_ci: str,
        key_errors: str,
        job_name: str,
        language: str,
        framework: str,
        error_type: str,
    ) -> str:
        """Build the LLM prompt for log-driven fixes.

        Encodes the same Nexus-only / 8-stage / docker-tags / Kaniko / Trivy
        invariants as the validation-driven prompt but asks the model to
        respond to a *real* job trace instead of a static linter list.
        """
        return f"""Fix the following GitLab CI/CD pipeline that failed at runtime.

## Error Information
- Job that failed: {job_name}
- Error type: {error_type}
- Language: {language}
- Framework: {framework}

## Error Log (last extracted lines)
```
{key_errors}
```

## Current Dockerfile
```dockerfile
{dockerfile}
```

## Current .gitlab-ci.yml
```yaml
{gitlab_ci}
```

## MANDATORY INVARIANTS (do not violate any of these)
1. Pipeline MUST have exactly the 8 stages (in order): compile, build, test, sast, quality, security, push, notify (a 9th `learn` stage is allowed for the `learn_record` job).
2. EVERY job MUST set `tags: [docker]`.
3. EVERY job image MUST be of the form `${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/<image>:<tag>`.
4. EVERY Dockerfile FROM line MUST be of the form `${{BASE_REGISTRY}}/apm-repo/demo/<image>:<tag>` (with `ARG BASE_REGISTRY=ai-nexus:5001` at the top).
5. The Kaniko `build_image` job MUST push to `${{NEXUS_INTERNAL_REGISTRY}}` and pass `--insecure --skip-tls-verify --insecure-registry=ai-nexus:5001`.
6. The Trivy `security` job MUST attach the trivy server as a service with `alias: trivy-server` and `command: ["server", "--listen", "0.0.0.0:8080"]`.
7. NEVER reference docker.io, gcr.io, quay.io, ghcr.io. Only Nexus.

## AVAILABLE NEXUS IMAGES
- amazoncorretto:17-alpine-jdk, eclipse-temurin:17-jre, maven:3.9-eclipse-temurin-17
- python:3.11-slim, python:3.12-slim
- node:18-alpine, node:20-alpine
- golang:1.21-alpine, golang:1.22-alpine
- rust:1.93-slim
- ruby:3.3-alpine
- php:8.3-fpm-alpine, php:8.2-cli, php:8.2-fpm-alpine
- perl:5.32-slim
- alpine:3.18, nginx:alpine
- kaniko-executor:debug
- aquasec-trivy:latest
- curlimages-curl:latest
- sonarsource-sonar-scanner-cli:5

## COMMON FIXES BY ERROR TYPE
- image_not_found: pick a tag that actually exists in Nexus from the list above; check that the image path uses ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/<name>:<tag>.
- service_connection: verify service alias names; trivy must be `trivy-server`, not localhost.
- missing_command: install the missing tool inside the script (e.g. `apt-get update && apt-get install -y curl`) or pick a base image that already has it.
- yaml_syntax: re-indent and re-quote suspicious values; preserve all 8 stages.
- auth_error: confirm `${{NEXUS_USERNAME}}/${{NEXUS_PASSWORD}}/${{SONAR_TOKEN}}/${{SPLUNK_HEC_TOKEN}}` references and that GitLab CI/CD variables exist.
- build_failure: align compile script to the language (mvn / npm / go build / cargo / pip / sbt / `perl Makefile.PL && make`).

## Output the fixed files in this EXACT format:

=== .gitlab-ci.yml ===
<complete fixed gitlab-ci.yml here>

=== Dockerfile ===
<complete fixed Dockerfile here>

=== EXPLANATION ===
<one paragraph: what you changed and why>
"""

    def _parse_log_fix_output(
        self,
        text: str,
        error_type: str,
        original_gitlab_ci: str,
        original_dockerfile: str,
    ) -> FixResult:
        """Parse the log-driven fix response into a ``FixResult``.

        Falls back to fenced-code-block extraction when the explicit
        ``=== .gitlab-ci.yml ===`` markers are missing.
        """
        gitlab_ci, dockerfile = self._parse_fix_response(
            response=text,
            original_gitlab_ci="",
            original_dockerfile="",
        )

        # _parse_fix_response returns the originals it was given when nothing
        # parsed. Because we passed empty defaults, anything still empty here
        # legitimately means the LLM output had no parseable block.
        gitlab_ci = gitlab_ci or None
        dockerfile = dockerfile or None

        # Extra fallback: hunt for fenced yaml/dockerfile blocks anywhere
        if not gitlab_ci:
            yaml_match = re.search(r'```ya?ml\s*(.*?)```', text, re.DOTALL)
            if yaml_match:
                candidate = self._strip_code_fences(yaml_match.group(1).strip())
                if 'stages:' in candidate:
                    gitlab_ci = candidate
        if not dockerfile:
            df_match = re.search(r'```dockerfile\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
            if df_match:
                candidate = self._strip_code_fences(df_match.group(1).strip())
                if 'FROM' in candidate.upper() or 'ARG' in candidate.upper():
                    dockerfile = candidate

        # Pull explanation block if present
        expl_match = re.search(
            r'===\s*EXPLANATION\s*===\s*(.+)$',
            text,
            re.DOTALL | re.IGNORECASE,
        )
        explanation = expl_match.group(1).strip() if expl_match else "Fix applied"
        # Strip trailing fence noise
        explanation = self._strip_code_fences(explanation)[:1000]

        # Determine which files actually changed
        changes_made: List[str] = []
        if gitlab_ci and gitlab_ci.strip() != (original_gitlab_ci or '').strip():
            changes_made.append("gitlab_ci_modified")
        if dockerfile and dockerfile.strip() != (original_dockerfile or '').strip():
            changes_made.append("dockerfile_modified")

        success = bool(gitlab_ci or dockerfile)

        return FixResult(
            success=success,
            gitlab_ci=gitlab_ci or original_gitlab_ci,
            dockerfile=dockerfile or original_dockerfile,
            explanation=explanation,
            error_type=error_type,
            changes_made=changes_made,
        )

    async def fix_from_run_log(
        self,
        dockerfile: str,
        gitlab_ci: str,
        project_id: int,
        pipeline_id: int,
        gitlab_token: str,
        language: str,
        framework: str,
    ) -> FixResult:
        """Pull the trace of the first failed job in a GitLab pipeline and
        generate a fix from its log.

        Uses ``settings.gitlab_url`` as the API base so the call works from
        inside the docker network (``http://gitlab-server`` by default).
        """
        api_base = self.gitlab_url.rstrip('/')
        headers = {"PRIVATE-TOKEN": gitlab_token}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                jobs_resp = await client.get(
                    f"{api_base}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs",
                    headers=headers,
                    params={"per_page": 100},
                )
                if jobs_resp.status_code != 200:
                    return FixResult(
                        success=False,
                        gitlab_ci=None,
                        dockerfile=None,
                        explanation=(
                            f"GET /pipelines/{pipeline_id}/jobs returned "
                            f"{jobs_resp.status_code}"
                        ),
                        error_type="fetch_error",
                        changes_made=[],
                    )

                jobs = jobs_resp.json() or []
                failed_job = next(
                    (j for j in jobs if j.get("status") == "failed"),
                    None,
                )
                if not failed_job:
                    return FixResult(
                        success=False,
                        gitlab_ci=None,
                        dockerfile=None,
                        explanation="No failed job found in pipeline",
                        error_type="unknown_error",
                        changes_made=[],
                    )

                job_name = failed_job.get("name", "unknown")
                job_id = failed_job.get("id")

                trace_resp = await client.get(
                    f"{api_base}/api/v4/projects/{project_id}/jobs/{job_id}/trace",
                    headers=headers,
                )
                if trace_resp.status_code != 200:
                    return FixResult(
                        success=False,
                        gitlab_ci=None,
                        dockerfile=None,
                        explanation=(
                            f"GET /jobs/{job_id}/trace returned "
                            f"{trace_resp.status_code}"
                        ),
                        error_type="fetch_error",
                        changes_made=[],
                    )

                trace_text = trace_resp.text or ""
                # Truncate to last 8000 chars; that's roughly where the
                # actionable failure tail lives.
                if len(trace_text) > 8000:
                    trace_text = trace_text[-8000:]

            return await self.generate_fix(
                dockerfile=dockerfile,
                gitlab_ci=gitlab_ci,
                error_log=trace_text,
                job_name=job_name,
                language=language,
                framework=framework,
            )
        except Exception as e:
            return FixResult(
                success=False,
                gitlab_ci=None,
                dockerfile=None,
                explanation=f"Failed to fetch trace: {e}",
                error_type="fetch_error",
                changes_made=[],
            )


# Singleton instance
gitlab_llm_fixer = GitLabLLMFixer()
