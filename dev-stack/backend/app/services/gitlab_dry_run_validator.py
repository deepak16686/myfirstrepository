"""
GitLab CI/CD Pipeline Dry Run Validator

Validates GitLab CI/CD pipeline YAML before committing using:
1. Local YAML syntax validation
2. Local structure validation
3. GitLab CI Lint API for server-side validation
"""
import re
import yaml
import httpx
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from app.config import settings


@dataclass
class ValidationResult:
    """Result of a validation check"""
    valid: bool
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings
        }


class GitLabDryRunValidator:
    """
    Validates GitLab CI/CD pipelines before committing.

    Performs:
    1. YAML syntax validation
    2. Dockerfile syntax validation
    3. Pipeline structure validation
    4. GitLab CI lint API validation (server-side)
    5. Stage dependency validation
    6. Variable and image validation
    """

    REQUIRED_STAGES = [
        'compile', 'build', 'test', 'sast', 'quality', 'security', 'push', 'notify'
    ]

    REQUIRED_VARIABLES = [
        'NEXUS_REGISTRY', 'NEXUS_PULL_REGISTRY', 'NEXUS_INTERNAL_REGISTRY',
        'IMAGE_NAME', 'IMAGE_TAG'
    ]

    NEXUS_PULL_REGISTRY = "localhost:5001"
    NEXUS_INTERNAL_REGISTRY = "ai-nexus:5001"

    def __init__(self):
        self.gitlab_url = settings.gitlab_url
        self.gitlab_token = settings.gitlab_token

    async def validate_all(
        self,
        gitlab_ci: str,
        dockerfile: str,
        gitlab_token: str = None,
        project_path: str = None
    ) -> Dict[str, ValidationResult]:
        """Run all validations and return comprehensive results."""
        token = gitlab_token or self.gitlab_token
        results = {}

        # 1. Validate YAML syntax
        results['yaml_syntax'] = self.validate_yaml_syntax(gitlab_ci)

        # 2. Validate Dockerfile syntax
        results['dockerfile_syntax'] = self.validate_dockerfile_syntax(dockerfile)

        # 3. Validate pipeline structure
        results['pipeline_structure'] = self.validate_pipeline_structure(gitlab_ci)

        # 4. Validate stage dependencies
        results['stage_dependencies'] = self.validate_stage_dependencies(gitlab_ci)

        # 5. Validate images use Nexus registry
        results['nexus_images'] = self.validate_nexus_images(gitlab_ci, dockerfile)

        # 6. GitLab CI Lint API validation (server-side)
        if token:
            results['gitlab_lint'] = await self.validate_with_gitlab_lint(
                gitlab_ci, token, project_path
            )

        return results

    def validate_yaml_syntax(self, yaml_content: str) -> ValidationResult:
        """Validate YAML syntax"""
        errors = []
        warnings = []

        try:
            parsed = yaml.safe_load(yaml_content)
            if parsed is None:
                errors.append("YAML content is empty or invalid")
            elif not isinstance(parsed, dict):
                errors.append("YAML root must be a dictionary/mapping")
        except yaml.YAMLError as e:
            errors.append(f"YAML syntax error: {str(e)}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_dockerfile_syntax(self, dockerfile: str) -> ValidationResult:
        """Validate Dockerfile syntax"""
        errors = []
        warnings = []

        if not dockerfile or not dockerfile.strip():
            errors.append("Dockerfile is empty")
            return ValidationResult(valid=False, errors=errors, warnings=warnings)

        # Remove markdown code blocks if present
        dockerfile = dockerfile.strip()
        if dockerfile.startswith('```'):
            lines = dockerfile.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            dockerfile = '\n'.join(lines)

        lines = dockerfile.strip().split('\n')
        has_from = False

        valid_instructions = {
            'FROM', 'RUN', 'CMD', 'LABEL', 'EXPOSE', 'ENV', 'ADD', 'COPY',
            'ENTRYPOINT', 'VOLUME', 'USER', 'WORKDIR', 'ARG', 'ONBUILD',
            'STOPSIGNAL', 'HEALTHCHECK', 'SHELL'
        }

        for i, line in enumerate(lines, 1):
            line = line.strip()

            if not line or line.startswith('#'):
                continue

            if line.upper().startswith('FROM'):
                has_from = True

            parts = line.split(None, 1)
            if parts:
                instruction = parts[0].upper()
                if instruction == 'ARG' and not has_from:
                    continue
                if instruction not in valid_instructions and not instruction.startswith('#'):
                    if not line.startswith(' ') and not line.startswith('\t'):
                        warnings.append(f"Line {i}: Unknown instruction '{instruction}'")

        if not has_from:
            errors.append("Dockerfile must have a FROM instruction")

        # Check for ARG BASE_REGISTRY
        if 'ARG BASE_REGISTRY' not in dockerfile:
            warnings.append("Missing ARG BASE_REGISTRY for Nexus registry")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_pipeline_structure(self, gitlab_ci: str) -> ValidationResult:
        """Validate GitLab CI pipeline structure"""
        errors = []
        warnings = []

        try:
            parsed = yaml.safe_load(gitlab_ci)
            if not parsed:
                errors.append("Pipeline content is empty")
                return ValidationResult(valid=False, errors=errors, warnings=warnings)

            # Check stages
            stages = parsed.get('stages', [])
            if not stages:
                errors.append("Missing 'stages' definition")
            else:
                for required_stage in self.REQUIRED_STAGES:
                    if required_stage not in stages:
                        warnings.append(f"Missing recommended stage: '{required_stage}'")

            # Check variables
            variables = parsed.get('variables', {})
            if not variables:
                warnings.append("Missing 'variables' section")
            else:
                for required_var in self.REQUIRED_VARIABLES:
                    if required_var not in variables:
                        warnings.append(f"Missing recommended variable: '{required_var}'")

            # Check for jobs
            reserved_keys = {'stages', 'variables', 'include', 'default', 'workflow', 'image', 'services', 'before_script', 'after_script', 'cache'}
            jobs = {k: v for k, v in parsed.items() if k not in reserved_keys and isinstance(v, dict)}

            if not jobs:
                errors.append("No jobs defined in pipeline")
            else:
                for job_name, job in jobs.items():
                    if isinstance(job, dict):
                        # Check job has stage
                        if 'stage' not in job:
                            warnings.append(f"Job '{job_name}' missing 'stage' definition")

                        # Check job has tags
                        if 'tags' not in job:
                            warnings.append(f"Job '{job_name}' missing 'tags' (should have [docker])")

                        # Check job has image or uses default
                        if 'image' not in job and 'default' not in parsed:
                            warnings.append(f"Job '{job_name}' missing 'image' definition")

        except yaml.YAMLError as e:
            errors.append(f"YAML parse error: {str(e)}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_stage_dependencies(self, gitlab_ci: str) -> ValidationResult:
        """Validate job stage assignments and dependencies"""
        errors = []
        warnings = []

        try:
            parsed = yaml.safe_load(gitlab_ci)
            if not parsed:
                return ValidationResult(valid=True, errors=errors, warnings=warnings)

            stages = parsed.get('stages', [])
            reserved_keys = {'stages', 'variables', 'include', 'default', 'workflow', 'image', 'services', 'before_script', 'after_script', 'cache'}
            jobs = {k: v for k, v in parsed.items() if k not in reserved_keys and isinstance(v, dict)}

            for job_name, job in jobs.items():
                if isinstance(job, dict):
                    job_stage = job.get('stage')
                    if job_stage and job_stage not in stages:
                        errors.append(f"Job '{job_name}' uses undefined stage '{job_stage}'")

                    # Check needs
                    needs = job.get('needs', [])
                    if isinstance(needs, list):
                        for need in needs:
                            need_job = need if isinstance(need, str) else need.get('job')
                            if need_job and need_job not in jobs:
                                errors.append(f"Job '{job_name}' needs non-existent job '{need_job}'")

        except yaml.YAMLError:
            pass

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_nexus_images(self, gitlab_ci: str, dockerfile: str) -> ValidationResult:
        """Validate that all images use Nexus private registry"""
        errors = []
        warnings = []

        # Check gitlab-ci.yml for public registry usage
        public_registries = ['docker.io', 'gcr.io', 'ghcr.io', 'quay.io', 'mcr.microsoft.com']

        for registry in public_registries:
            if registry in gitlab_ci:
                warnings.append(f"Pipeline uses public registry '{registry}' - should use Nexus")

        # Check dockerfile for public registry usage
        if dockerfile:
            for registry in public_registries:
                if registry in dockerfile:
                    warnings.append(f"Dockerfile uses public registry '{registry}' - should use Nexus")

            # Check FROM statements
            from_pattern = r'FROM\s+(?!.*\$\{?BASE_REGISTRY\}?)([^\s]+)'
            matches = re.findall(from_pattern, dockerfile, re.IGNORECASE)
            for match in matches:
                if 'ai-nexus' not in match and 'localhost' not in match and '${' not in match:
                    warnings.append(f"Dockerfile FROM '{match}' should use Nexus registry")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def validate_with_gitlab_lint(
        self,
        gitlab_ci: str,
        gitlab_token: str,
        project_path: str = None
    ) -> ValidationResult:
        """
        Validate pipeline using GitLab CI Lint API.

        Uses two approaches:
        1. Project-specific lint (if project_path provided): /api/v4/projects/:id/ci/lint
        2. Global lint: /api/v4/ci/lint
        """
        errors = []
        warnings = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"PRIVATE-TOKEN": gitlab_token}

            # Try project-specific lint first if project_path provided
            if project_path:
                encoded_path = project_path.replace('/', '%2F')
                lint_url = f"{self.gitlab_url}/api/v4/projects/{encoded_path}/ci/lint"

                try:
                    response = await client.post(
                        lint_url,
                        headers=headers,
                        json={"content": gitlab_ci}
                    )

                    if response.status_code == 200:
                        result = response.json()
                        if not result.get('valid', False):
                            lint_errors = result.get('errors', [])
                            for err in lint_errors:
                                errors.append(f"GitLab Lint: {err}")
                            warnings.extend(result.get('warnings', []))
                        else:
                            # Check for merged yaml issues
                            if result.get('merged_yaml'):
                                print("[GitLab Lint] Pipeline valid - merged YAML available")
                        return ValidationResult(
                            valid=len(errors) == 0,
                            errors=errors,
                            warnings=warnings
                        )
                except Exception as e:
                    print(f"[GitLab Lint] Project lint failed: {e}, trying global lint")

            # Fallback to global lint
            lint_url = f"{self.gitlab_url}/api/v4/ci/lint"
            try:
                response = await client.post(
                    lint_url,
                    headers=headers,
                    json={"content": gitlab_ci}
                )

                if response.status_code == 200:
                    result = response.json()
                    if not result.get('valid', False):
                        lint_errors = result.get('errors', [])
                        for err in lint_errors:
                            errors.append(f"GitLab Lint: {err}")
                        warnings.extend(result.get('warnings', []))
                elif response.status_code == 401:
                    warnings.append("GitLab Lint: Authentication failed - skipping server validation")
                else:
                    warnings.append(f"GitLab Lint: API returned status {response.status_code}")

            except httpx.TimeoutException:
                warnings.append("GitLab Lint: Request timed out")
            except Exception as e:
                warnings.append(f"GitLab Lint: {str(e)}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def get_validation_summary(
        self,
        results: Dict[str, ValidationResult]
    ) -> tuple:
        """Get a summary of all validation results."""
        all_valid = True
        all_errors = []
        all_warnings = []

        for check_name, result in results.items():
            if not result.valid:
                all_valid = False
            all_errors.extend([f"[{check_name}] {e}" for e in result.errors])
            all_warnings.extend([f"[{check_name}] {w}" for w in result.warnings])

        summary = ""
        if all_errors:
            summary += "ERRORS:\n" + "\n".join(f"  - {e}" for e in all_errors) + "\n"
        if all_warnings:
            summary += "WARNINGS:\n" + "\n".join(f"  - {w}" for w in all_warnings)

        if not summary:
            summary = "All validations passed!"

        return all_valid, summary


# Singleton instance
gitlab_dry_run_validator = GitLabDryRunValidator()
