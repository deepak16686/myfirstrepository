"""
File: github_llm_fixer.py
Purpose: Uses the configured LLM (Ollama or Claude Code CLI) to analyze GitHub Actions workflow
    validation errors or runtime failure logs and generate corrected workflow YAML and Dockerfile.
    Implements an iterative fix-and-validate loop (up to N attempts) that repeatedly validates,
    identifies errors, prompts the LLM for fixes, and re-validates until the workflow passes.
When Used: Called by generate_with_validation() after initial generation when the workflow needs
    iterative fixing (Priority 3 path for unknown languages), and by the self-healing workflow and
    /fix endpoint when a committed workflow fails at runtime and needs log-based repair.
Why Created: Mirrors the Jenkins LLM fixer pattern as a standalone service. Kept outside the
    github_pipeline package because it is also used directly by the router and the self-healing
    workflow without going through the generator facade.
"""
import re
import httpx
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass

from app.config import settings
from app.integrations.llm_provider import get_llm_provider, get_active_provider_name


@dataclass
class FixResult:
    """Result of an LLM fix attempt"""
    success: bool
    workflow: Optional[str]
    dockerfile: Optional[str]
    explanation: str
    error_type: str
    changes_made: list


class GitHubLLMFixer:
    """
    Uses LLM to fix failed GitHub Actions workflows.
    """

    FIX_MODEL = "pipeline-generator-v5"

    # Common error patterns and their types
    ERROR_PATTERNS = {
        r'manifest unknown|image not found|not found': 'image_not_found',
        r'connection refused|ECONNREFUSED': 'service_connection',
        r'command not found|not found:': 'missing_command',
        r'build failed|error:|Error:': 'build_failure',
        r'permission denied|EACCES': 'permission_error',
        r'timeout|timed out': 'timeout_error',
        r'artifact.*not found|no artifacts': 'artifact_missing',
        r'yaml.*error|syntax error|parse error': 'yaml_syntax',
        r'authentication.*failed|401|403': 'auth_error',
        r'out of memory|OOM': 'resource_error',
        r'exec:.*node.*not found|node.*executable.*not found': 'missing_nodejs',
        r'exec:.*docker.*not found|docker.*executable.*not found': 'missing_docker_cli',
        r'TLS handshake|certificate|ssl|tls_network_error': 'tls_network_error',
        r'GHESNotSupportedError|not currently supported on GHES': 'ghes_unsupported',
    }

    def __init__(self):
        self.ollama_url = settings.ollama_url

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Strip markdown code fences from extracted content."""
        text = re.sub(r'^```\w*\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)
        return text.strip()

    def identify_error_type(self, error_log: str) -> str:
        """Identify the type of error from log output"""
        error_log_lower = error_log.lower()

        for pattern, error_type in self.ERROR_PATTERNS.items():
            if re.search(pattern, error_log_lower):
                return error_type

        return 'unknown_error'

    def extract_key_errors(self, error_log: str, max_lines: int = 50) -> str:
        """Extract the most relevant error lines from a log"""
        lines = error_log.split('\n')
        error_lines = []

        error_keywords = [
            'error', 'failed', 'exception', 'fatal',
            'cannot', 'unable', 'not found', 'denied'
        ]

        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in error_keywords):
                error_lines.append(line.strip())

        # If no specific errors found, take the last N lines
        if not error_lines:
            error_lines = [l.strip() for l in lines[-max_lines:] if l.strip()]

        return '\n'.join(error_lines[:max_lines])

    async def generate_fix(
        self,
        dockerfile: str,
        workflow: str,
        error_log: str,
        job_name: str,
        language: str,
        framework: str
    ) -> FixResult:
        """Generate a fix for the failed workflow using LLM"""
        error_type = self.identify_error_type(error_log)
        key_errors = self.extract_key_errors(error_log)

        prompt = self._build_fix_prompt(
            dockerfile, workflow, key_errors, job_name,
            language, framework, error_type
        )

        try:
            llm = get_llm_provider()
            response = await llm.generate(
                model=self.FIX_MODEL,
                prompt=prompt,
                options={
                    "temperature": 0.1,
                    "num_predict": 6000
                }
            )
            await llm.close()

            generated_text = response.get("response", "")
            return self._parse_fix_output(
                generated_text, error_type, dockerfile, workflow
            )

        except Exception as e:
            return FixResult(
                success=False,
                workflow=None,
                dockerfile=None,
                explanation=f"LLM fix generation failed: {str(e)}",
                error_type=error_type,
                changes_made=[]
            )

        return FixResult(
            success=False,
            workflow=None,
            dockerfile=None,
            explanation="Failed to generate fix",
            error_type=error_type,
            changes_made=[]
        )

    def _build_fix_prompt(
        self,
        dockerfile: str,
        workflow: str,
        error_log: str,
        job_name: str,
        language: str,
        framework: str,
        error_type: str
    ) -> str:
        """Build prompt for LLM to fix the workflow"""
        prompt = f"""Fix the following GitHub Actions workflow that failed.

## Error Information
- Job that failed: {job_name}
- Error type: {error_type}
- Language: {language}
- Framework: {framework}

## Error Log
```
{error_log}
```

## Current Dockerfile
```dockerfile
{dockerfile}
```

## Current Workflow (.github/workflows/ci.yml)
```yaml
{workflow}
```

## Fix Requirements
1. ALL images must come from Nexus registry: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/<image>
2. Use self-hosted runners
3. Ensure proper artifact handling between jobs
4. Fix the specific error shown in the logs
5. Jobs using `container:` MUST use images with Node.js (GitHub Actions JS actions need it)
6. Jobs WITHOUT `container:` should use shell commands (docker login/build/push/run)

## Available Nexus Images (use -node20 variants for container jobs):
- maven:3.9-eclipse-temurin-17-node20 (Java - for container jobs)
- python:3.11-slim-node20 (Python - for container jobs)
- node:20-slim (Node.js)
- golang:1.22-bullseye-node20 (Go - for container jobs)
- sonarsource-sonar-scanner-cli:5 (SonarQube)
- aquasec-trivy:latest (Trivy)

## Common Fixes by Error Type
- image_not_found: Check image name matches available images in Nexus
- service_connection: Verify service URLs and network access
- build_failure: Check build commands for the language
- artifact_missing: Ensure upload-artifact and download-artifact paths match
- auth_error: Verify credentials are correctly passed
- "node: executable file not found": Container image lacks Node.js - use -node20 image variant
- "exec: docker: not found": Use shell `docker` commands on host, not inside container
- "GHESNotSupportedError" or "ECONNREFUSED" on artifact: Remove upload-artifact/download-artifact entirely. Use actions/checkout in each job instead.

Output the fixed files in this format:

---EXPLANATION---
(Brief explanation of what you fixed)
---DOCKERFILE---
(Complete fixed Dockerfile)
---GITHUB_ACTIONS---
(Complete fixed .github/workflows/ci.yml)
---END---
"""
        return prompt

    def _parse_fix_output(
        self,
        text: str,
        error_type: str,
        original_dockerfile: str,
        original_workflow: str
    ) -> FixResult:
        """Parse LLM output to extract fixed files"""
        # Extract explanation
        explanation_match = re.search(
            r'---EXPLANATION---\s*(.*?)\s*(?:---DOCKERFILE---|---GITHUB_ACTIONS---|---END---)',
            text, re.DOTALL
        )
        explanation = explanation_match.group(1).strip() if explanation_match else "Fix applied"

        # Extract Dockerfile
        dockerfile_match = re.search(
            r'---DOCKERFILE---\s*(.*?)\s*(?:---GITHUB_ACTIONS---|---END---)',
            text, re.DOTALL
        )
        dockerfile = self._strip_code_fences(dockerfile_match.group(1).strip()) if dockerfile_match else None

        # Extract workflow
        workflow_match = re.search(
            r'---GITHUB_ACTIONS---\s*(.*?)\s*---END---',
            text, re.DOTALL
        )
        workflow = self._strip_code_fences(workflow_match.group(1).strip()) if workflow_match else None

        # Fallback to code block extraction
        if not workflow:
            yaml_match = re.search(r'```ya?ml\s*(.*?)\s*```', text, re.DOTALL)
            if yaml_match:
                workflow = yaml_match.group(1).strip()

        if not dockerfile:
            docker_match = re.search(r'```dockerfile\s*(.*?)\s*```', text, re.DOTALL)
            if docker_match:
                dockerfile = docker_match.group(1).strip()

        # Determine what changed
        changes_made = []
        if dockerfile and dockerfile != original_dockerfile:
            changes_made.append("dockerfile_modified")
        if workflow and workflow != original_workflow:
            changes_made.append("workflow_modified")

        success = bool(workflow or dockerfile)

        return FixResult(
            success=success,
            workflow=workflow or original_workflow,
            dockerfile=dockerfile or original_dockerfile,
            explanation=explanation,
            error_type=error_type,
            changes_made=changes_made
        )

    async def fix_pipeline(
        self,
        workflow: str,
        dockerfile: str,
        errors: list,
        warnings: list,
        analysis: Dict[str, Any],
        model: str = None
    ) -> Dict[str, str]:
        """
        Fix workflow using LLM based on validation errors.
        Used by iterative_fix() loop.
        """
        model = model or self.FIX_MODEL

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
You must fix the following GitHub Actions workflow that has validation errors.

## PROJECT INFO:
- Language: {analysis.get('language', 'unknown')}
- Framework: {analysis.get('framework', 'generic')}
- Package Manager: {analysis.get('package_manager', 'unknown')}

{error_context}
{warning_context}

## CURRENT WORKFLOW (WITH ERRORS):
```yaml
{workflow}
```

## CURRENT DOCKERFILE:
```dockerfile
{dockerfile}
```

## MANDATORY RULES FOR FIX:
1. ALL images MUST use Nexus registry: ${{{{ env.NEXUS_REGISTRY }}}}/apm-repo/demo/<image>:<tag>
2. ALL Dockerfile FROM statements MUST use: ${{{{BASE_REGISTRY}}}}/apm-repo/demo/<image>:<tag>
3. Workflow MUST have these jobs: compile, build-image, test-image, static-analysis, sonarqube, trivy-scan, push-release, notify-success, notify-failure, learn-record
4. ALL jobs MUST use: runs-on: self-hosted
5. Use proper GitHub Actions syntax with 'on:', 'jobs:', 'steps:' blocks
6. Use ${{{{ secrets.* }}}} for credentials and ${{{{ env.* }}}} for environment variables
7. notify-success and learn-record jobs depend on push-release
8. learn-record step: curl to ${{{{ env.DEVOPS_BACKEND_URL }}}}/api/v1/github-pipeline/learn/record
9. Dockerfile MUST use ARG BASE_REGISTRY=ai-nexus:5001
10. No public registries (docker.io, gcr.io, quay.io, ghcr.io)

## AVAILABLE NEXUS IMAGES:
- maven:3.9-eclipse-temurin-17 (Java/Maven builds - NO Node.js)
- maven:3.9-eclipse-temurin-17-node20 (Java/Maven builds WITH Node.js - USE THIS for container jobs)
- python:3.11-slim (Python - NO Node.js)
- python:3.11-slim-node20 (Python WITH Node.js - USE THIS for container jobs)
- node:20-slim (Node.js)
- golang:1.22-bullseye (Go - NO Node.js)
- golang:1.22-bullseye-node20 (Go WITH Node.js - USE THIS for container jobs)
- rust:1.93-slim (Rust)
- ruby:3.3-alpine (Ruby)
- php:8.3-fpm-alpine (PHP)
- dotnet-sdk:8.0 (.NET build)
- dotnet-aspnet:8.0-alpine (.NET runtime)
- sonarsource-sonar-scanner-cli:5 (SonarQube)
- aquasec-trivy:latest (Trivy)
- alpine:3.18 (Minimal base)
- nginx:alpine (Static file serving)
- eclipse-temurin:17-jre (Java runtime)

## IMPORTANT: Node.js is required inside container images for GitHub Actions (checkout, upload-artifact, etc.)
- Jobs using `container:` MUST use images with Node.js (e.g. maven:3.9-eclipse-temurin-17-node20)
- Jobs WITHOUT `container:` (running on host) should use shell commands: `docker login`, `docker build`, `docker push`, `docker run`
- Do NOT use docker/login-action, docker/build-push-action, docker/setup-buildx-action in jobs with `container:`

## CRITICAL: Gitea Actions compatibility
- Do NOT use actions/upload-artifact or actions/download-artifact (artifact service is broken on Gitea)
- Each job should be self-contained: use actions/checkout@v4 to get source, Dockerfile handles multi-stage builds
- actions/checkout@v4 is OK
- Error "GHESNotSupportedError" or "ECONNREFUSED 127.0.0.1" on artifact upload = remove artifact actions entirely

## RESPONSE FORMAT:
Return ONLY the fixed files:

---DOCKERFILE---
(fixed Dockerfile content)
---GITHUB_ACTIONS---
(fixed workflow content)
---END---
"""

        llm = get_llm_provider()

        try:
            response = await llm.generate(
                prompt=prompt,
                model=model
            )

            response_text = response.get('response', '')
            parsed = self._parse_fix_output(response_text, "validation", dockerfile, workflow)

            return {
                'workflow': parsed.workflow or workflow,
                'dockerfile': parsed.dockerfile or dockerfile,
                'raw_response': response_text
            }

        except Exception as e:
            print(f"[GitHub LLM Fixer] Error fixing workflow: {e}")
            return {
                'workflow': workflow,
                'dockerfile': dockerfile,
                'error': str(e)
            }
        finally:
            await llm.close()

    async def iterative_fix(
        self,
        workflow: str,
        dockerfile: str,
        analysis: Dict[str, Any],
        max_attempts: int = 10,
        model: str = None
    ) -> Dict[str, Any]:
        """
        Iteratively fix workflow until validation passes or max attempts reached.
        """
        current_workflow = workflow
        current_dockerfile = dockerfile
        fix_history = []

        for attempt in range(1, max_attempts + 1):
            print(f"[GitHub LLM Fixer] Attempt {attempt}/{max_attempts}")

            errors, warnings = self._validate_workflow(current_workflow, current_dockerfile)

            fix_history.append({
                'attempt': attempt,
                'valid': len(errors) == 0,
                'errors': errors,
                'warnings': warnings
            })

            if not errors:
                print(f"[GitHub LLM Fixer] Workflow valid after {attempt} attempt(s)")
                return {
                    'success': True,
                    'workflow': current_workflow,
                    'dockerfile': current_dockerfile,
                    'attempts': attempt,
                    'fix_history': fix_history,
                    'has_warnings': len(warnings) > 0,
                    'fixer_model_used': get_active_provider_name()
                }

            if attempt < max_attempts:
                print(f"[GitHub LLM Fixer] Fixing {len(errors)} errors...")
                fix_result = await self.fix_pipeline(
                    current_workflow,
                    current_dockerfile,
                    errors,
                    warnings,
                    analysis,
                    model
                )

                if 'error' not in fix_result:
                    current_workflow = fix_result['workflow']
                    current_dockerfile = fix_result['dockerfile']

        print(f"[GitHub LLM Fixer] Max attempts ({max_attempts}) reached")
        return {
            'success': False,
            'workflow': current_workflow,
            'dockerfile': current_dockerfile,
            'attempts': max_attempts,
            'fix_history': fix_history,
            'final_errors': errors,
            'fixer_model_used': get_active_provider_name()
        }

    def _validate_workflow(self, workflow: str, dockerfile: str) -> Tuple[List[str], List[str]]:
        """Basic text-based validation of GitHub Actions workflow and Dockerfile."""
        errors = []
        warnings = []

        if not workflow or not workflow.strip():
            errors.append("Workflow is empty")
            return errors, warnings

        # Check YAML structure
        if 'on:' not in workflow and 'on :' not in workflow:
            errors.append("Missing 'on:' trigger block")
        if 'jobs:' not in workflow:
            errors.append("Missing 'jobs:' block")

        # Check for self-hosted runners
        if 'runs-on:' in workflow and 'self-hosted' not in workflow:
            errors.append("Jobs must use 'runs-on: self-hosted' (not ubuntu-latest or other)")

        # Check for public registry references
        public_registries = ['docker.io/', 'gcr.io/', 'quay.io/', 'ghcr.io/']
        for reg in public_registries:
            if reg in workflow:
                errors.append(f"Public registry reference found: {reg}")

        # Check required jobs
        required_jobs = ['compile', 'build-image', 'test-image', 'static-analysis',
                        'sonarqube', 'trivy-scan', 'push-release']
        for job in required_jobs:
            if f'{job}:' not in workflow and f'"{job}"' not in workflow and f"'{job}'" not in workflow:
                warnings.append(f"Missing job: {job}")

        # Check env block
        if 'NEXUS_REGISTRY' not in workflow:
            warnings.append("Missing NEXUS_REGISTRY in env/secrets")

        # Dockerfile validation
        if dockerfile:
            if 'FROM' not in dockerfile.upper():
                errors.append("Dockerfile missing FROM statement")
            for reg in ['docker.io/', 'gcr.io/', 'quay.io/']:
                if reg in dockerfile:
                    errors.append(f"Dockerfile uses public registry: {reg}")

        return errors, warnings

    async def fix_from_run_log(
        self,
        dockerfile: str,
        workflow: str,
        run_id: int,
        owner: str,
        repo: str,
        github_token: str,
        language: str,
        framework: str
    ) -> FixResult:
        """Fetch logs from workflow run and generate fix"""
        try:
            from app.integrations.github import GitHubIntegration
            from app.config import ToolConfig

            config = ToolConfig(
                base_url=settings.github_url,
                token=github_token
            )
            github = GitHubIntegration(config)

            # Get jobs for the run
            jobs = await github.get_workflow_run_jobs(owner, repo, run_id)

            # Find failed job
            failed_job = None
            for job in jobs:
                if job.get("conclusion") == "failure":
                    failed_job = job
                    break

            if not failed_job:
                return FixResult(
                    success=False,
                    workflow=None,
                    dockerfile=None,
                    explanation="No failed job found in workflow run",
                    error_type="unknown",
                    changes_made=[]
                )

            # Get logs for failed job
            job_id = failed_job["id"]
            job_name = failed_job.get("name", "unknown")
            logs = await github.get_job_logs(owner, repo, job_id)

            await github.close()

            # Generate fix
            return await self.generate_fix(
                dockerfile=dockerfile,
                workflow=workflow,
                error_log=logs,
                job_name=job_name,
                language=language,
                framework=framework
            )

        except Exception as e:
            return FixResult(
                success=False,
                workflow=None,
                dockerfile=None,
                explanation=f"Failed to fetch logs: {str(e)}",
                error_type="fetch_error",
                changes_made=[]
            )


# Singleton instance
github_llm_fixer = GitHubLLMFixer()
