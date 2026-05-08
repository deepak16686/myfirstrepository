"""
File: validator.py
Purpose: Performs text-based validation and automatic fixing of generated Jenkinsfiles and
    Dockerfiles. Checks for required structural elements (pipeline/agent/stages blocks,
    environment credentials, post block), replaces public registry references with Nexus
    URLs, fixes HTTPS to HTTP for the HTTP-only Nexus registry, corrects agent labels,
    and adds missing ARG BASE_REGISTRY to Dockerfiles.
When Used: Called by the generator after LLM generation (priority 3 path) to sanitize and
    repair the LLM output before returning it to the user. Also used as a fallback to return
    default templates when the generated content is empty or structurally invalid.
Why Created: Extracted from the generator to isolate validation and post-processing rules
    from generation logic. Unlike the GitLab pipeline validator (which uses the GitLab CI
    lint API), this module uses text-based checks because Jenkinsfiles are Groovy and have
    no remote lint endpoint.
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

    # 9. Ensure || true on non-critical commands (sonar-scanner, trivy, static analysis)
    fixed = _ensure_error_tolerance(fixed)

    # 10. Ensure --entrypoint="" for images with custom entrypoints (trivy, sonar-scanner)
    fixed = _ensure_entrypoint_override(fixed)

    return fixed


def _ensure_error_tolerance(jenkinsfile: str) -> str:
    """Ensure non-critical commands have || true to prevent pipeline failures.

    SonarQube, Trivy, and static analysis tools should never block the pipeline.
    This works at the sh command level (not image references) by matching
    sh '...' / sh "..." / sh triple-quote blocks that contain non-critical commands.
    """
    if not jenkinsfile:
        return jenkinsfile

    non_critical_cmds = [
        'sonar-scanner', 'trivy ', 'trivy\t',
        'spotbugs:', 'pmd:', 'checkstyle:',
        'bandit ', 'pylint ', 'flake8 ', 'eslint ',
        'go vet', 'cargo clippy', 'brakeman ', 'phpstan ',
    ]

    def _needs_fix(text):
        """Check if text contains a non-critical command without || true."""
        for cmd in non_critical_cmds:
            if cmd in text and '|| true' not in text:
                return True
        return False

    result = jenkinsfile

    # Pattern 1: sh 'single-line command' (single quotes)
    def fix_sh_single(m):
        prefix, content, suffix = m.group(1), m.group(2), m.group(3)
        if _needs_fix(content):
            return f"{prefix}{content} || true{suffix}"
        return m.group(0)
    result = re.sub(r"(sh\s+')((?:[^'\\]|\\.)*?)(')", fix_sh_single, result)

    # Pattern 2: sh "single-line command" (double quotes)
    def fix_sh_double(m):
        prefix, content, suffix = m.group(1), m.group(2), m.group(3)
        if _needs_fix(content):
            return f"{prefix}{content} || true{suffix}"
        return m.group(0)
    result = re.sub(r'(sh\s+")((?:[^"\\]|\\.)*?)(")', fix_sh_double, result)

    # Pattern 3: sh '''multi-line''' or sh """multi-line"""
    def fix_sh_triple(m):
        prefix, content, suffix = m.group(1), m.group(2), m.group(3)
        if _needs_fix(content):
            # Add || true before the closing triple-quote on the last command line
            lines = content.rstrip().split('\n')
            # Find last non-empty line (before closing quotes)
            for i in range(len(lines) - 1, -1, -1):
                stripped = lines[i].strip()
                if stripped and not stripped.startswith('#'):
                    if '|| true' not in lines[i] and not stripped.endswith('\\'):
                        lines[i] = lines[i].rstrip() + ' || true'
                    break
            return f"{prefix}{chr(10).join(lines)}{suffix}"
        return m.group(0)
    result = re.sub(r"(sh\s+''')(.*?)(''')", fix_sh_triple, result, flags=re.DOTALL)
    result = re.sub(r'(sh\s+""")(.*?)(""")', fix_sh_triple, result, flags=re.DOTALL)

    return result


def _ensure_entrypoint_override(jenkinsfile: str) -> str:
    """Ensure Docker agents using images with custom entrypoints have --entrypoint="" args.

    Images like aquasec-trivy and sonarsource-sonar-scanner-cli have custom ENTRYPOINT
    that conflicts with Jenkins shell commands. Adding args '--entrypoint=""' fixes this.
    """
    if not jenkinsfile:
        return jenkinsfile

    # Images that need --entrypoint="" override
    entrypoint_images = ['aquasec-trivy', 'sonar-scanner-cli']

    for img_pattern in entrypoint_images:
        # Find docker agent blocks that reference this image
        # Pattern: image "...{img_pattern}..." followed by optional args
        # We need to add args '--entrypoint=""' if not already present
        pattern = re.compile(
            r"(image\s+[\"'].*?" + re.escape(img_pattern) + r".*?[\"']\s*\n)"
            r"(\s*registryUrl.*?\n)?"
            r"(\s*registryCredentialsId.*?\n)?"
            r"(\s*reuseNode.*?\n)?",
            re.DOTALL
        )

        for match in pattern.finditer(jenkinsfile):
            block = match.group(0)
            # Check if args '--entrypoint=""' already exists nearby
            end_pos = match.end()
            next_100 = jenkinsfile[end_pos:end_pos + 100]
            if "--entrypoint" not in block and "--entrypoint" not in next_100:
                # Find where to insert args (after reuseNode or registryCredentialsId or image line)
                insert_after = block.rstrip()
                indent = "                    "
                # Detect indent from the image line
                img_line = match.group(1)
                leading = len(img_line) - len(img_line.lstrip())
                indent = " " * leading
                new_block = block.rstrip() + "\n" + indent + "args '--entrypoint=\"\"'" + "\n"
                jenkinsfile = jenkinsfile.replace(block, new_block, 1)

    return jenkinsfile


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
