"""
LLM Fixer Service

Uses LLM (Ollama) to automatically fix failed pipeline configurations.
Analyzes error logs, identifies issues, and generates corrected files.
"""
import re
import json
import httpx
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from app.config import settings, tools_manager
from app.integrations.ollama import OllamaIntegration


@dataclass
class FixResult:
    """Result of an LLM fix attempt"""
    success: bool
    dockerfile: Optional[str]
    gitlab_ci: Optional[str]
    explanation: str
    error_identified: str
    fix_applied: str


class LLMFixer:
    """
    Uses LLM to analyze pipeline failures and generate fixes.

    This service:
    1. Parses error logs to identify the issue
    2. Queries available Nexus images
    3. Generates a fix prompt for the LLM
    4. Parses the LLM response to extract fixed files
    """

    # Model to use for fixing - can be different from generation model
    FIX_MODEL = "pipeline-generator-v5"

    # Common error patterns and their likely causes
    ERROR_PATTERNS = {
        r'manifest unknown|not found|MANIFEST_UNKNOWN': 'image_not_found',
        r'connection refused|cannot connect': 'service_connection',
        r'command not found|no such file': 'missing_command',
        r'compilation failed|build failed|compile error': 'build_failure',
        r'permission denied|access denied': 'permission_error',
        r'timeout|timed out': 'timeout_error',
        r'artifact.*not found|no artifacts': 'artifact_missing',
        r'yaml.*error|syntax error': 'yaml_syntax',
        r'invalid.*stage|unknown stage': 'invalid_stage',
    }

    def __init__(self):
        self.ollama_config = tools_manager.get_tool("ollama")
        self.gitlab_url = settings.gitlab_url
        self.nexus_url = "http://ai-nexus:5001"

    def _get_ollama(self) -> OllamaIntegration:
        return OllamaIntegration(self.ollama_config)

    async def analyze_error(self, error_log: str) -> Tuple[str, str]:
        """
        Analyze error log to identify the type and cause of failure.
        Returns (error_type, error_description)
        """
        error_log_lower = error_log.lower()

        for pattern, error_type in self.ERROR_PATTERNS.items():
            if re.search(pattern, error_log_lower):
                # Extract relevant error message
                lines = error_log.split('\n')
                relevant_lines = []
                for line in lines:
                    if re.search(pattern, line.lower()):
                        relevant_lines.append(line.strip())

                description = '\n'.join(relevant_lines[:5]) if relevant_lines else error_log[:500]
                return error_type, description

        return 'unknown_error', error_log[:500]

    async def get_available_nexus_images(self) -> List[str]:
        """Get list of available images from Nexus registry"""
        images = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Get catalog
                response = await client.get(f"{self.nexus_url}/v2/_catalog")
                if response.status_code == 200:
                    repos = response.json().get('repositories', [])

                    # Get tags for each repo (limit to common ones)
                    for repo in repos[:20]:
                        try:
                            tags_resp = await client.get(f"{self.nexus_url}/v2/{repo}/tags/list")
                            if tags_resp.status_code == 200:
                                tags = tags_resp.json().get('tags', [])
                                for tag in tags[:5]:  # Limit tags per repo
                                    images.append(f"{repo}:{tag}")
                        except:
                            pass
        except Exception as e:
            print(f"[LLMFixer] Error getting Nexus images: {e}")

        return images

    async def generate_fix(
        self,
        dockerfile: str,
        gitlab_ci: str,
        error_log: str,
        job_name: str,
        language: str,
        framework: str,
        repo_files: List[str] = None
    ) -> FixResult:
        """
        Use LLM to analyze error and generate fixed configuration files.
        """
        # Analyze the error
        error_type, error_description = await self.analyze_error(error_log)
        print(f"[LLMFixer] Identified error type: {error_type}")

        # Get available Nexus images
        available_images = await self.get_available_nexus_images()
        images_str = '\n'.join(f"  - {img}" for img in available_images[:30])

        # Build the fix prompt
        prompt = self._build_fix_prompt(
            dockerfile=dockerfile,
            gitlab_ci=gitlab_ci,
            error_log=error_log,
            error_type=error_type,
            error_description=error_description,
            job_name=job_name,
            language=language,
            framework=framework,
            available_images=images_str,
            repo_files=repo_files or []
        )

        # Call LLM
        try:
            ollama = self._get_ollama()
            response = await ollama.generate(
                model=self.FIX_MODEL,
                prompt=prompt,
                options={"temperature": 0.3}  # Lower temperature for more precise fixes
            )
            await ollama.close()

            llm_response = response.get('response', '')

            # Parse the response
            fixed_dockerfile, fixed_gitlab_ci, explanation = self._parse_fix_response(llm_response)

            if fixed_dockerfile or fixed_gitlab_ci:
                return FixResult(
                    success=True,
                    dockerfile=fixed_dockerfile or dockerfile,
                    gitlab_ci=fixed_gitlab_ci or gitlab_ci,
                    explanation=explanation,
                    error_identified=error_type,
                    fix_applied=f"Fixed {error_type}: {error_description[:100]}"
                )
            else:
                return FixResult(
                    success=False,
                    dockerfile=None,
                    gitlab_ci=None,
                    explanation="Could not parse LLM response",
                    error_identified=error_type,
                    fix_applied=""
                )

        except Exception as e:
            print(f"[LLMFixer] Error calling LLM: {e}")
            return FixResult(
                success=False,
                dockerfile=None,
                gitlab_ci=None,
                explanation=f"LLM error: {str(e)}",
                error_identified=error_type,
                fix_applied=""
            )

    def _build_fix_prompt(
        self,
        dockerfile: str,
        gitlab_ci: str,
        error_log: str,
        error_type: str,
        error_description: str,
        job_name: str,
        language: str,
        framework: str,
        available_images: str,
        repo_files: List[str]
    ) -> str:
        """Build the prompt for LLM to fix the pipeline"""

        # Truncate error log if too long
        if len(error_log) > 3000:
            error_log = error_log[-3000:]  # Last 3000 chars (most relevant)

        prompt = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                     PIPELINE FIX REQUEST - AUTO REPAIR                       ║
╚══════════════════════════════════════════════════════════════════════════════╝

## ERROR INFORMATION
- **Failed Job:** {job_name}
- **Error Type:** {error_type}
- **Language:** {language}
- **Framework:** {framework}

## ERROR LOG (Last portion):
```
{error_log}
```

## CURRENT DOCKERFILE:
```dockerfile
{dockerfile}
```

## CURRENT .gitlab-ci.yml:
```yaml
{gitlab_ci}
```

## AVAILABLE NEXUS IMAGES (USE ONLY THESE):
{available_images}

## PROJECT FILES:
{', '.join(repo_files[:20]) if repo_files else 'Not available'}

═══════════════════════════════════════════════════════════════════════════════
## YOUR TASK

Analyze the error and provide FIXED versions of the files.

### COMMON FIXES BY ERROR TYPE:

1. **image_not_found**:
   - Use an image from the AVAILABLE NEXUS IMAGES list above
   - Format: ${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/<image>:<tag>

2. **service_connection**:
   - Use correct hostnames: ai-nexus:5001, ai-sonarqube:9000, ai-splunk:8088
   - For Trivy, use service alias: trivy-server:8080

3. **build_failure**:
   - Check build commands match the language/framework
   - Java: mvn clean package -DskipTests
   - Python: pip install -r requirements.txt
   - Node.js: npm install && npm run build
   - Go: go build -o app ./...
   - Rust: cargo build --release (needs rust image, NOT maven)
   - Scala: sbt assembly or sbt package

4. **artifact_missing**:
   - Ensure compile stage produces artifacts in correct path
   - Check artifact paths match between stages

5. **yaml_syntax**:
   - Fix indentation (use 2 spaces)
   - Ensure proper quoting of special characters

### CRITICAL RULES:
- NEXUS_PULL_REGISTRY (localhost:5001) for job images
- NEXUS_INTERNAL_REGISTRY (ai-nexus:5001) for Kaniko destination
- All jobs need: tags: [docker]
- Use only images that exist in the AVAILABLE NEXUS IMAGES list
- The compile/build image MUST match the project language (e.g. rust image for Rust, maven for Java, node for Node.js)
- The Dockerfile MUST use the correct base image and build tools for the language (e.g. Cargo.toml → Rust, pom.xml → Java)
- Fix the ROOT CAUSE job, not just notification/downstream jobs

═══════════════════════════════════════════════════════════════════════════════
## OUTPUT FORMAT (MUST FOLLOW EXACTLY):

---EXPLANATION---
(Brief explanation of what was wrong and what you fixed)
---DOCKERFILE---
(Complete fixed Dockerfile - include ALL lines)
---GITLAB_CI---
(Complete fixed .gitlab-ci.yml - include ALL lines)
---END---

Provide the complete fixed files, not just the changes.
"""
        return prompt

    def _parse_fix_response(self, response: str) -> Tuple[Optional[str], Optional[str], str]:
        """
        Parse LLM response to extract fixed Dockerfile and .gitlab-ci.yml
        Returns (dockerfile, gitlab_ci, explanation)
        """
        dockerfile = None
        gitlab_ci = None
        explanation = ""

        try:
            # Extract explanation
            explanation_match = re.search(
                r'---EXPLANATION---\s*(.*?)\s*---DOCKERFILE---',
                response,
                re.DOTALL
            )
            if explanation_match:
                explanation = explanation_match.group(1).strip()

            # Extract Dockerfile
            dockerfile_match = re.search(
                r'---DOCKERFILE---\s*(.*?)\s*---GITLAB_CI---',
                response,
                re.DOTALL
            )
            if dockerfile_match:
                dockerfile = dockerfile_match.group(1).strip()
                # Clean up markdown code blocks if present
                dockerfile = re.sub(r'^```dockerfile?\s*', '', dockerfile)
                dockerfile = re.sub(r'\s*```$', '', dockerfile)

            # Extract GitLab CI
            gitlab_ci_match = re.search(
                r'---GITLAB_CI---\s*(.*?)\s*---END---',
                response,
                re.DOTALL
            )
            if gitlab_ci_match:
                gitlab_ci = gitlab_ci_match.group(1).strip()
                # Clean up markdown code blocks if present
                gitlab_ci = re.sub(r'^```ya?ml?\s*', '', gitlab_ci)
                gitlab_ci = re.sub(r'\s*```$', '', gitlab_ci)

            # Fallback: try to find yaml/dockerfile blocks if structured format failed
            if not dockerfile and not gitlab_ci:
                # Try to find any dockerfile content
                df_match = re.search(r'```dockerfile\s*(.*?)\s*```', response, re.DOTALL)
                if df_match:
                    dockerfile = df_match.group(1).strip()

                # Try to find any yaml content
                yaml_match = re.search(r'```ya?ml\s*(.*?)\s*```', response, re.DOTALL)
                if yaml_match:
                    gitlab_ci = yaml_match.group(1).strip()

        except Exception as e:
            print(f"[LLMFixer] Error parsing response: {e}")
            explanation = f"Parse error: {str(e)}"

        return dockerfile, gitlab_ci, explanation

    async def fix_validation_errors(
        self,
        dockerfile: str,
        gitlab_ci: str,
        validation_errors: List[str],
        language: str,
        framework: str
    ) -> FixResult:
        """
        Fix validation errors (dry-run failures) before committing.
        This is called when dry-run validation fails.
        """
        error_log = "DRY RUN VALIDATION FAILED:\n" + "\n".join(f"- {e}" for e in validation_errors)

        return await self.generate_fix(
            dockerfile=dockerfile,
            gitlab_ci=gitlab_ci,
            error_log=error_log,
            job_name="dry_run_validation",
            language=language,
            framework=framework
        )

    async def fix_from_job_log(
        self,
        dockerfile: str,
        gitlab_ci: str,
        job_id: int,
        project_id: int,
        gitlab_token: str,
        language: str,
        framework: str
    ) -> FixResult:
        """
        Fetch job log from GitLab and generate a fix.
        """
        # Fetch job details and log
        job_name = "unknown"
        error_log = ""

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get job details
                job_resp = await client.get(
                    f"{self.gitlab_url}/api/v4/projects/{project_id}/jobs/{job_id}",
                    headers={"PRIVATE-TOKEN": gitlab_token}
                )
                if job_resp.status_code == 200:
                    job_data = job_resp.json()
                    job_name = job_data.get('name', 'unknown')

                # Get job log
                log_resp = await client.get(
                    f"{self.gitlab_url}/api/v4/projects/{project_id}/jobs/{job_id}/trace",
                    headers={"PRIVATE-TOKEN": gitlab_token}
                )
                if log_resp.status_code == 200:
                    error_log = log_resp.text

        except Exception as e:
            print(f"[LLMFixer] Error fetching job log: {e}")
            error_log = f"Could not fetch job log: {str(e)}"

        return await self.generate_fix(
            dockerfile=dockerfile,
            gitlab_ci=gitlab_ci,
            error_log=error_log,
            job_name=job_name,
            language=language,
            framework=framework
        )


# Singleton instance
llm_fixer = LLMFixer()
