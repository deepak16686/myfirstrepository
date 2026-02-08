"""
GitLab Pipeline LLM Fixer

Uses Ollama LLM to fix pipeline errors based on validation results.
Implements iterative fix-and-validate cycle.
"""
import re
from typing import Dict, Any, Optional, Tuple
import httpx

from app.config import tools_manager
from app.integrations.ollama import OllamaIntegration
from app.integrations.llm_provider import get_llm_provider


class GitLabLLMFixer:
    """
    Uses LLM to fix GitLab CI/CD pipeline errors.

    Flow:
    1. Receives pipeline YAML with validation errors
    2. Constructs prompt with errors and best practices
    3. Gets LLM to fix the issues
    4. Returns corrected pipeline
    """

    FIX_MODEL = "pipeline-generator-v5"  # Same model used for generation

    def __init__(self):
        self.ollama_config = tools_manager.get_tool("ollama")

    def _get_llm(self):
        """Get the configured LLM provider (Ollama or Claude Code)."""
        return get_llm_provider()

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
        """Parse the LLM response to extract fixed files."""

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
        model: str = None
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
        current_gitlab_ci = gitlab_ci
        current_dockerfile = dockerfile
        fix_history = []

        for attempt in range(1, max_attempts + 1):
            print(f"[LLM Fixer] Attempt {attempt}/{max_attempts}")

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
                    'fix_history': fix_history
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
                    'has_warnings': True
                }

            # Try to fix errors
            if attempt < max_attempts:
                print(f"[LLM Fixer] Fixing {len(all_errors)} errors...")
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
            'final_errors': all_errors
        }


# Singleton instance
gitlab_llm_fixer = GitLabLLMFixer()
