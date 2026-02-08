"""
GitHub Actions LLM Fixer

Uses LLM to analyze workflow failures and generate fixes.
"""
import re
import httpx
from typing import Dict, Any, Optional
from dataclasses import dataclass

from app.config import settings
from app.integrations.llm_provider import get_llm_provider


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

    FIX_MODEL = "github-actions-generator-v1"

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
    }

    def __init__(self):
        self.ollama_url = settings.ollama_url

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

## Common Fixes by Error Type
- image_not_found: Check image name matches available images in Nexus
- service_connection: Verify service URLs and network access
- build_failure: Check build commands for the language
- artifact_missing: Ensure upload-artifact and download-artifact paths match
- auth_error: Verify credentials are correctly passed

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
        dockerfile = dockerfile_match.group(1).strip() if dockerfile_match else None

        # Extract workflow
        workflow_match = re.search(
            r'---GITHUB_ACTIONS---\s*(.*?)\s*---END---',
            text, re.DOTALL
        )
        workflow = workflow_match.group(1).strip() if workflow_match else None

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
