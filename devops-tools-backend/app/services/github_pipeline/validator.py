"""
Validation and fixing functions for GitHub Actions workflows and Dockerfiles.
"""
import re
import yaml
from typing import Dict, Any, Optional

from app.services.github_pipeline.default_templates import _get_default_workflow, _get_default_dockerfile


def _validate_and_fix_workflow(
    workflow: str,
    reference: Optional[str]
) -> str:
    """Validate and fix common issues in generated workflow"""
    try:
        parsed = yaml.safe_load(workflow)
        if not parsed:
            return _get_default_workflow({"language": "java", "framework": "generic"}, "self-hosted")

        # Ensure env block exists with required variables
        if 'env' not in parsed:
            parsed['env'] = {}

        required_env = {
            'NEXUS_REGISTRY': '${{ secrets.NEXUS_REGISTRY }}',
            'NEXUS_INTERNAL_REGISTRY': '${{ secrets.NEXUS_INTERNAL_REGISTRY }}',
            'NEXUS_USERNAME': '${{ secrets.NEXUS_USERNAME }}',
            'NEXUS_PASSWORD': '${{ secrets.NEXUS_PASSWORD }}',
            'IMAGE_NAME': '${{ github.event.repository.name }}',
            'IMAGE_TAG': '"1.0.${{ github.run_number }}"',
            'SONARQUBE_URL': '${{ secrets.SONARQUBE_URL }}',
            'SPLUNK_HEC_URL': '${{ secrets.SPLUNK_HEC_URL }}',
            'DEVOPS_BACKEND_URL': '${{ secrets.DEVOPS_BACKEND_URL }}'
        }

        for key, value in required_env.items():
            if key not in parsed['env']:
                parsed['env'][key] = value

        # Ensure jobs exist
        if 'jobs' not in parsed:
            parsed['jobs'] = {}

        # Ensure all jobs use self-hosted runner
        for job_name, job in parsed.get('jobs', {}).items():
            if isinstance(job, dict):
                if 'runs-on' not in job:
                    job['runs-on'] = 'self-hosted'

        return yaml.dump(parsed, default_flow_style=False, sort_keys=False)

    except Exception as e:
        print(f"[Validate] Error: {e}")
        return workflow


def _validate_and_fix_dockerfile(dockerfile: str, language: str) -> str:
    """Validate and fix Dockerfile"""
    if not dockerfile or not dockerfile.strip():
        return _get_default_dockerfile({"language": language, "framework": "generic"})

    lines = dockerfile.strip().split('\n')
    fixed_lines = []
    has_arg = False
    has_from = False

    for line in lines:
        # Check for ARG BASE_REGISTRY
        if line.strip().upper().startswith('ARG BASE_REGISTRY'):
            has_arg = True
        if line.strip().upper().startswith('FROM'):
            has_from = True

        # Replace public registry references
        if 'docker.io' in line or 'gcr.io' in line or 'quay.io' in line:
            line = re.sub(
                r'(FROM\s+)(docker\.io|gcr\.io|quay\.io)/([^\s]+)',
                r'\1${BASE_REGISTRY}/apm-repo/demo/\3',
                line
            )

        fixed_lines.append(line)

    # Add ARG if missing
    if not has_arg and has_from:
        fixed_lines.insert(0, 'ARG BASE_REGISTRY=ai-nexus:5001')

    return '\n'.join(fixed_lines)
