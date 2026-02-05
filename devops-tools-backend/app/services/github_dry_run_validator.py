"""
GitHub Actions Dry Run Validator

Validates GitHub Actions workflow and Dockerfile before committing.
"""
import re
import yaml
from typing import Dict, Any, List
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


class GitHubDryRunValidator:
    """
    Validates GitHub Actions workflows before committing.

    Performs:
    1. YAML syntax validation
    2. Dockerfile syntax validation
    3. Workflow structure validation
    4. Job dependencies validation
    5. Secrets usage validation
    """

    REQUIRED_JOBS = [
        'compile', 'build-image', 'test-image', 'static-analysis',
        'sonarqube', 'trivy-scan', 'push-release', 'notify-success',
        'notify-failure', 'learn-record'
    ]

    REQUIRED_ENV_VARS = [
        'NEXUS_REGISTRY', 'NEXUS_USERNAME', 'NEXUS_PASSWORD',
        'IMAGE_NAME', 'IMAGE_TAG'
    ]

    def __init__(self):
        self.nexus_url = "http://localhost:5001"

    async def validate_all(
        self,
        workflow: str,
        dockerfile: str,
        github_token: str = None
    ) -> Dict[str, ValidationResult]:
        """Run all validations and return comprehensive results."""
        results = {}

        # Validate YAML syntax
        results['yaml_syntax'] = self.validate_yaml_syntax(workflow)

        # Validate Dockerfile syntax
        results['dockerfile_syntax'] = self.validate_dockerfile_syntax(dockerfile)

        # Validate workflow structure
        results['workflow_structure'] = self.validate_workflow_structure(workflow)

        # Validate job dependencies
        results['job_dependencies'] = self.validate_job_dependencies(workflow)

        # Validate secrets usage
        results['secrets_usage'] = self.validate_secrets_usage(workflow)

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

    def validate_workflow_structure(self, workflow: str) -> ValidationResult:
        """Validate GitHub Actions workflow structure"""
        errors = []
        warnings = []

        try:
            parsed = yaml.safe_load(workflow)
            if not parsed:
                errors.append("Workflow content is empty")
                return ValidationResult(valid=False, errors=errors, warnings=warnings)

            # Check 'on' trigger
            if 'on' not in parsed:
                errors.append("Missing 'on' trigger definition")

            # Check jobs
            jobs = parsed.get('jobs', {})
            if not jobs:
                errors.append("Missing 'jobs' definition")
            else:
                # Check for required jobs
                for required_job in self.REQUIRED_JOBS:
                    if required_job not in jobs:
                        warnings.append(f"Missing recommended job: '{required_job}'")

                # Check job structure
                for job_name, job in jobs.items():
                    if isinstance(job, dict):
                        if 'runs-on' not in job:
                            warnings.append(f"Job '{job_name}' missing 'runs-on'")
                        if 'steps' not in job:
                            warnings.append(f"Job '{job_name}' missing 'steps'")

            # Check env variables
            env = parsed.get('env', {})
            for required_var in self.REQUIRED_ENV_VARS:
                if required_var not in env:
                    warnings.append(f"Missing recommended env variable: '{required_var}'")

        except yaml.YAMLError as e:
            errors.append(f"YAML parse error: {str(e)}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_job_dependencies(self, workflow: str) -> ValidationResult:
        """Validate job dependencies (needs) are valid"""
        errors = []
        warnings = []

        try:
            parsed = yaml.safe_load(workflow)
            if not parsed:
                return ValidationResult(valid=True, errors=errors, warnings=warnings)

            jobs = parsed.get('jobs', {})
            job_names = set(jobs.keys())

            for job_name, job in jobs.items():
                if isinstance(job, dict):
                    needs = job.get('needs', [])
                    if isinstance(needs, str):
                        needs = [needs]

                    for needed_job in needs:
                        if needed_job not in job_names:
                            errors.append(
                                f"Job '{job_name}' depends on non-existent job '{needed_job}'"
                            )

        except yaml.YAMLError:
            pass

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_secrets_usage(self, workflow: str) -> ValidationResult:
        """Validate secrets are properly referenced"""
        errors = []
        warnings = []

        # Check for common secret patterns
        required_secrets = [
            'NEXUS_REGISTRY', 'NEXUS_USERNAME', 'NEXUS_PASSWORD'
        ]

        for secret in required_secrets:
            if f'secrets.{secret}' not in workflow:
                warnings.append(f"Secret '{secret}' not referenced in workflow")

        # Check for hardcoded credentials (security warning)
        credential_patterns = [
            r'password\s*[:=]\s*["\'][^$][^"\']+["\']',
            r'token\s*[:=]\s*["\'][^$][^"\']+["\']',
        ]

        for pattern in credential_patterns:
            if re.search(pattern, workflow, re.IGNORECASE):
                warnings.append("Possible hardcoded credentials detected - use secrets instead")
                break

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
github_dry_run_validator = GitHubDryRunValidator()
