"""
Validation and fixing functions for Jenkinsfiles and Dockerfiles.

Uses text-based validation since Jenkinsfiles are Groovy (not YAML).
"""
import re
from typing import Optional

from app.services.jenkins_pipeline.default_templates import _get_default_jenkinsfile, _get_default_dockerfile


def _validate_and_fix_jenkinsfile(
    jenkinsfile: str,
    reference: Optional[str]
) -> str:
    """Validate and fix common issues in generated Jenkinsfile"""
    if not jenkinsfile or not jenkinsfile.strip():
        return _get_default_jenkinsfile({"language": "java", "framework": "generic"}, "any")

    fixed = jenkinsfile.strip()

    # 1. Ensure pipeline { } wrapper exists
    if 'pipeline' not in fixed or 'pipeline {' not in fixed.replace('pipeline{', 'pipeline {'):
        return _get_default_jenkinsfile({"language": "java", "framework": "generic"}, "any")

    # 2. Ensure agent directive exists
    if 'agent' not in fixed:
        # Insert agent after pipeline {
        fixed = fixed.replace('pipeline {', "pipeline {\n    agent any", 1)

    # 3. Ensure stages block exists
    if 'stages {' not in fixed and 'stages{' not in fixed:
        return _get_default_jenkinsfile({"language": "java", "framework": "generic"}, "any")

    # 4. Ensure environment block has required credentials
    required_creds = [
        ("NEXUS_REGISTRY", "credentials('nexus-registry-url')"),
        ("NEXUS_CREDS", "credentials('nexus-credentials')"),
        ("IMAGE_NAME", None),
        ("IMAGE_TAG", None),
    ]
    for cred_name, _ in required_creds:
        if cred_name not in fixed:
            # If environment block missing entirely, add it
            if 'environment {' not in fixed and 'environment{' not in fixed:
                fixed = fixed.replace(
                    'stages {',
                    "environment {\n        NEXUS_REGISTRY = credentials('nexus-registry-url')\n        NEXUS_CREDS = credentials('nexus-credentials')\n        IMAGE_NAME = '${env.JOB_NAME}'.split('/').last().toLowerCase()\n        IMAGE_TAG = \"1.0.${BUILD_NUMBER}\"\n    }\n\n    stages {",
                    1
                )
                break

    # 5. Ensure post block exists
    if 'post {' not in fixed and 'post{' not in fixed:
        # Insert post block before final closing brace
        last_brace = fixed.rfind('}')
        if last_brace > 0:
            post_block = """
    post {
        failure {
            sh \"\"\"
                curl -sk -X POST "${SPLUNK_HEC_URL}/services/collector" \\\\
                  -H "Authorization: Splunk ${SPLUNK_HEC_TOKEN}" \\\\
                  -H "Content-Type: application/json" \\\\
                  -d '{"event":{"message":"Pipeline failed","pipeline":"${BUILD_NUMBER}","project":"${IMAGE_NAME}","status":"FAILURE"},"sourcetype":"jenkins:pipeline","source":"${IMAGE_NAME}"}'
            \"\"\"
        }
        always {
            cleanWs()
        }
    }
"""
            fixed = fixed[:last_brace] + post_block + fixed[last_brace:]

    # 6. Replace public registry references
    public_registries = ['docker.io/', 'gcr.io/', 'quay.io/', 'ghcr.io/', 'registry.hub.docker.com/']
    for registry in public_registries:
        if registry in fixed:
            fixed = fixed.replace(registry, '${NEXUS_REGISTRY}/apm-repo/demo/')

    # 7. Fix HTTPS → HTTP for Nexus (HTTP-only registry)
    fixed = fixed.replace('https://${NEXUS_REGISTRY}', 'http://${NEXUS_REGISTRY}')

    # 8. Fix agent label 'any' → 'docker'
    fixed = re.sub(r"agent\s*\{\s*label\s*'any'\s*\}", "agent { label 'docker' }", fixed)

    return fixed


def _validate_and_fix_dockerfile(dockerfile: str, language: str) -> str:
    """Validate and fix Dockerfile"""
    if not dockerfile or not dockerfile.strip():
        return _get_default_dockerfile({"language": language, "framework": "generic"})

    lines = dockerfile.strip().split('\n')
    fixed_lines = []
    has_arg = False
    has_from = False

    for line in lines:
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
        fixed_lines.insert(0, 'ARG BASE_REGISTRY=localhost:5001')

    result = '\n'.join(fixed_lines)

    # Fix ai-nexus:5001 → localhost:5001 (container DNS unreachable from host Docker)
    result = result.replace('ai-nexus:5001', 'localhost:5001')

    return result
