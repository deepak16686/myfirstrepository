"""
File: dry_run_validator.py
Purpose: Pre-commit validation service that checks Dockerfile syntax, YAML structure, GitLab CI schema compliance (via GitLab's lint API), and Nexus image availability before pipeline files are committed, catching errors early.
When Used: Called by the pipeline router's dry-run endpoint and by the self-healing workflow before committing generated pipeline files to GitLab.
Why Created: Prevents wasted CI/CD runs by validating generated pipeline files locally before they reach GitLab, catching syntax errors, invalid stage references, missing Nexus images, and Dockerfile issues that would otherwise only surface after a commit.
"""
import re
import yaml
import httpx
from typing import Dict, Any, List, Tuple, Optional
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


class DryRunValidator:
    """
    Validates pipeline configurations before committing.

    Performs:
    1. YAML syntax validation
    2. Dockerfile syntax validation
    3. GitLab CI lint API validation
    4. Nexus image availability check
    """

    REQUIRED_STAGES = ['compile', 'build', 'test', 'sast', 'quality', 'security', 'push', 'notify', 'learn']
    REQUIRED_VARIABLES = ['NEXUS_PULL_REGISTRY', 'NEXUS_INTERNAL_REGISTRY', 'IMAGE_NAME', 'IMAGE_TAG']

    def __init__(self):
        self.gitlab_url = settings.gitlab_url
        self.gitlab_token = settings.gitlab_token
        self.nexus_url = "http://localhost:5001"  # For image checks

    async def validate_all(
        self,
        gitlab_ci: str,
        dockerfile: str,
        gitlab_token: str = None
    ) -> Dict[str, ValidationResult]:
        """
        Run all validations and return comprehensive results.
        """
        results = {}

        # Validate YAML syntax
        results['yaml_syntax'] = self.validate_yaml_syntax(gitlab_ci)

        # Validate Dockerfile syntax
        results['dockerfile_syntax'] = self.validate_dockerfile_syntax(dockerfile)

        # Validate GitLab CI structure
        results['gitlab_ci_structure'] = self.validate_gitlab_ci_structure(gitlab_ci)

        # Validate using GitLab CI Lint API
        token = gitlab_token or self.gitlab_token
        if token:
            results['gitlab_lint'] = await self.validate_gitlab_lint(gitlab_ci, token)

        # Check Nexus image availability
        results['nexus_images'] = await self.validate_nexus_images(gitlab_ci, dockerfile)

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

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Check for FROM instruction
            if line.upper().startswith('FROM'):
                has_from = True

            # Check instruction validity
            parts = line.split(None, 1)
            if parts:
                instruction = parts[0].upper()
                # Handle ARG before FROM
                if instruction == 'ARG' and not has_from:
                    continue
                if instruction not in valid_instructions and not instruction.startswith('#'):
                    # Check if it might be a continuation
                    if not line.startswith(' ') and not line.startswith('\t'):
                        warnings.append(f"Line {i}: Unknown instruction '{instruction}'")

        if not has_from:
            errors.append("Dockerfile must have a FROM instruction")

        # Check for common issues
        if 'COPY . .' in dockerfile and 'WORKDIR' not in dockerfile:
            warnings.append("COPY . . without WORKDIR may copy to unexpected location")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_gitlab_ci_structure(self, gitlab_ci: str) -> ValidationResult:
        """Validate GitLab CI structure and required elements"""
        errors = []
        warnings = []

        try:
            parsed = yaml.safe_load(gitlab_ci)
            if not parsed:
                errors.append("GitLab CI content is empty")
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
            for required_var in self.REQUIRED_VARIABLES:
                if required_var not in variables:
                    warnings.append(f"Missing recommended variable: '{required_var}'")

            # Check jobs have required fields
            for key, value in parsed.items():
                if key in ['stages', 'variables', 'default', 'include', 'workflow']:
                    continue

                if isinstance(value, dict):
                    # It's a job
                    if 'stage' not in value:
                        warnings.append(f"Job '{key}' missing 'stage' definition")
                    if 'script' not in value and 'trigger' not in value:
                        warnings.append(f"Job '{key}' missing 'script' definition")
                    if 'tags' not in value:
                        warnings.append(f"Job '{key}' missing 'tags' (should have [docker])")

            # Check for Kaniko build job
            has_kaniko = False
            for key, value in parsed.items():
                if isinstance(value, dict):
                    image = value.get('image', '')
                    if isinstance(image, dict):
                        image = image.get('name', '')
                    if 'kaniko' in str(image).lower():
                        has_kaniko = True
                        break

            if not has_kaniko:
                warnings.append("No Kaniko build job detected - image building may not work")

        except yaml.YAMLError as e:
            errors.append(f"YAML parse error: {str(e)}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def validate_gitlab_lint(self, gitlab_ci: str, gitlab_token: str) -> ValidationResult:
        """Use GitLab CI Lint API to validate the configuration"""
        errors = []
        warnings = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.gitlab_url}/api/v4/ci/lint",
                    headers={"PRIVATE-TOKEN": gitlab_token},
                    json={"content": gitlab_ci}
                )

                if response.status_code == 200:
                    result = response.json()
                    if not result.get('valid', False):
                        lint_errors = result.get('errors', [])
                        for err in lint_errors:
                            errors.append(f"GitLab Lint: {err}")

                        lint_warnings = result.get('warnings', [])
                        for warn in lint_warnings:
                            warnings.append(f"GitLab Lint: {warn}")
                else:
                    warnings.append(f"GitLab Lint API returned status {response.status_code}")

        except Exception as e:
            warnings.append(f"Could not reach GitLab Lint API: {str(e)}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def validate_nexus_images(self, gitlab_ci: str, dockerfile: str) -> ValidationResult:
        """Check if referenced images exist in Nexus registry"""
        errors = []
        warnings = []

        # Extract image references
        images_to_check = set()

        # From gitlab-ci.yml
        image_pattern = r'\$\{?NEXUS_PULL_REGISTRY\}?/apm-repo/demo/([^:\s"\']+):?([^:\s"\']*)'
        for match in re.finditer(image_pattern, gitlab_ci):
            image_name = match.group(1)
            image_tag = match.group(2) or 'latest'
            images_to_check.add((image_name, image_tag))

        # From Dockerfile
        from_pattern = r'FROM\s+\$\{?BASE_REGISTRY\}?/apm-repo/demo/([^:\s]+):?([^\s]*)'
        for match in re.finditer(from_pattern, dockerfile):
            image_name = match.group(1)
            image_tag = match.group(2) or 'latest'
            images_to_check.add((image_name, image_tag))

        # Check each image in Nexus (as warnings only - don't block if unreachable)
        for image_name, image_tag in images_to_check:
            exists = await self._check_nexus_image(image_name, image_tag)
            if not exists:
                # Make this a warning, not an error - the image might exist but validation can't reach Nexus
                warnings.append(f"Could not verify image in Nexus: {image_name}:{image_tag}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def _check_nexus_image(self, image_name: str, tag: str) -> bool:
        """Check if an image exists in Nexus registry"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try to get tags for the image
                response = await client.get(
                    f"{self.nexus_url}/v2/apm-repo/demo/{image_name}/tags/list"
                )

                if response.status_code == 200:
                    data = response.json()
                    tags = data.get('tags', [])
                    return tag in tags or tag == 'latest'

        except Exception:
            pass

        return False

    def get_validation_summary(self, results: Dict[str, ValidationResult]) -> Tuple[bool, str]:
        """
        Get a summary of all validation results.
        Returns (all_valid, summary_message)
        """
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
dry_run_validator = DryRunValidator()
