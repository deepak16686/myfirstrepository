"""
File: validator.py
Purpose: Validates and auto-corrects generated .gitlab-ci.yml and Dockerfile content using
    a comprehensive set of guardrails. Enforces required stages, Nexus registry usage, correct
    language-specific images, proper YAML escaping, Kaniko auth formatting, and the presence
    of the RL learn stage. Also provides helper functions for extracting code blocks from
    LLM markdown output.
When Used: Called immediately after LLM generation (or ChromaDB template retrieval) to
    sanitize the output before it reaches the user or gets committed. Every pipeline passes
    through validate_and_fix_pipeline_images and _validate_and_fix_pipeline before being
    returned from the generator.
Why Created: Extracted from the monolithic pipeline_generator.py to isolate the extensive
    validation and auto-correction logic (10+ guardrails, image fixers, code block extractors)
    into a dedicated module, reducing the generator file from 3291 lines and making the
    validation rules independently testable and maintainable.
"""
import re
from typing import Optional

from .constants import (
    LANGUAGE_COMPILE_IMAGES,
    LANGUAGE_DOCKERFILE_IMAGES,
    LANGUAGE_COMPILE_COMMANDS,
)


def _ensure_learn_stage(pipeline_yaml: str) -> str:
    """
    Ensure the pipeline has the 'learn' stage for RL recording.
    This is added to ALL pipelines (including those from RL storage) so that
    successful pipelines can be recorded for future improvements.
    """
    if not pipeline_yaml:
        return pipeline_yaml

    # Check if learn stage already exists WITH the actual API call
    # A learn_record job with only echo statements is a dummy — needs the curl call
    has_learn_stage = '- learn' in pipeline_yaml
    has_learn_job = 'learn_record:' in pipeline_yaml
    has_learn_curl = '/api/v1/pipeline/learn/record' in pipeline_yaml

    if has_learn_stage and has_learn_job and has_learn_curl:
        return pipeline_yaml

    # If learn_record exists but is a dummy (no curl call), replace it
    if has_learn_job and not has_learn_curl:
        # Remove the existing dummy learn_record job:
        # Matches optional comment lines + learn_record: + all indented/empty lines following it
        pipeline_yaml = re.sub(
            r'(#[^\n]*\n)*learn_record:\n(?:[ \t]+[^\n]*\n|[ \t]*\n)*',
            '',
            pipeline_yaml
        )
        # Reset the flag since we removed it
        has_learn_job = False

    # Add learn stage to stages list if not present
    if '- learn' not in pipeline_yaml:
        # Find the stages section and add learn after notify using regex
        # Handle various formats: "- notify\n", "- notify\n\n", etc.
        pattern = r'(- notify)\s*(\n)'
        replacement = r'\1\n  - learn  # Reinforcement Learning - records successful pipeline for future use\2'
        pipeline_yaml = re.sub(pattern, replacement, pipeline_yaml, count=1)

    # Add DEVOPS_BACKEND_URL variable if not present
    if 'DEVOPS_BACKEND_URL' not in pipeline_yaml:
        # Find SPLUNK_HEC_URL line and add after it using regex
        pattern = r'(SPLUNK_HEC_URL:\s*"http://ai-splunk:8088")\s*\n'
        replacement = r'\1\n  # DevOps Backend for RL (Reinforcement Learning)\n  DEVOPS_BACKEND_URL: "http://devops-tools-backend:8003"\n'
        pipeline_yaml = re.sub(pattern, replacement, pipeline_yaml, count=1)

    # Add learn_record job if not present
    if 'learn_record:' not in pipeline_yaml:
        learn_job = '''
# ============================================================================
# REINFORCEMENT LEARNING - Record successful pipeline configuration
# ============================================================================
learn_record:
  stage: learn
  image: ${NEXUS_PULL_REGISTRY}/apm-repo/demo/curlimages-curl:latest
  tags: [docker]
  script:
    - echo "=============================================="
    - echo "REINFORCEMENT LEARNING - Recording Success"
    - echo "=============================================="
    - echo "Pipeline ${CI_PIPELINE_ID} completed successfully!"
    - echo "Recording configuration for future AI improvements..."
    - 'curl -s -X POST "${DEVOPS_BACKEND_URL}/api/v1/pipeline/learn/record" -H "Content-Type: application/json" -d "{\\"repo_url\\":\\"${CI_PROJECT_URL}\\",\\"gitlab_token\\":\\"${GITLAB_TOKEN}\\",\\"branch\\":\\"${CI_COMMIT_REF_NAME}\\",\\"pipeline_id\\":${CI_PIPELINE_ID}}" && echo " SUCCESS: Configuration recorded for RL" || echo " Note: RL recording skipped"'
    - echo "=============================================="
    - echo "This pipeline config will help generate better"
    - echo "pipelines for similar projects in the future!"
    - echo "=============================================="
  when: on_success
  allow_failure: true
'''
        pipeline_yaml = pipeline_yaml.rstrip() + learn_job

    return pipeline_yaml


def validate_and_fix_pipeline_images(
    gitlab_ci: str, dockerfile: str, language: str, analysis: dict = None
) -> tuple:
    """
    Validate that pipeline images match the project language and fix if wrong.
    This catches cases where the LLM generates a pipeline with wrong images
    (e.g., using maven image for a Rust project).

    If `analysis` dict is provided and contains `resolved_compile_image` /
    `resolved_runtime_image` from deep analysis, those take priority over the
    static LANGUAGE_*_IMAGES constants.  This ensures that version-specific
    images (e.g., maven:3.9-eclipse-temurin-21 for Java 21) are used.

    Returns (fixed_gitlab_ci, fixed_dockerfile, corrections_made)
    """
    import re as _re
    lang = language.lower()
    corrections = []

    # Prefer dynamically resolved images from deep analysis over static constants
    correct_compile_image = (
        (analysis or {}).get("resolved_compile_image")
        or LANGUAGE_COMPILE_IMAGES.get(lang)
    )
    correct_dockerfile_image = (
        (analysis or {}).get("resolved_compile_image")
        or LANGUAGE_DOCKERFILE_IMAGES.get(lang)
    )
    correct_commands = LANGUAGE_COMPILE_COMMANDS.get(lang)

    if not correct_compile_image:
        # Unknown language - skip image-specific corrections but still return
        # The LLM (v5) handles unknown languages; validation will catch issues
        print(f"[ImageValidator] Language '{language}' not in known image map - relying on LLM-generated images")
        return gitlab_ci, dockerfile, corrections

    nexus_prefix = "${NEXUS_PULL_REGISTRY}/apm-repo/demo/"
    full_correct_image = f"{nexus_prefix}{correct_compile_image}"

    # -- Fix .gitlab-ci.yml compile job image --
    # Find compile job and check its image
    wrong_image_patterns = []
    for other_lang, img in LANGUAGE_COMPILE_IMAGES.items():
        if other_lang != lang and img != correct_compile_image:
            wrong_image_patterns.append(_re.escape(img))

    if wrong_image_patterns:
        wrong_pattern = '|'.join(wrong_image_patterns)
        # Replace wrong images in compile/sast/quality stages with correct one
        for wrong_img_match in _re.finditer(
            rf'(\${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/)({wrong_pattern})',
            gitlab_ci
        ):
            old_full = wrong_img_match.group(0)
            gitlab_ci = gitlab_ci.replace(old_full, full_correct_image)
            corrections.append(
                f"CI: Replaced {wrong_img_match.group(2)} with {correct_compile_image} for {language}"
            )

    # Also fix hardcoded wrong images (without variable)
    for other_lang, img in LANGUAGE_COMPILE_IMAGES.items():
        if other_lang != lang and img != correct_compile_image:
            hardcoded = f"localhost:5001/apm-repo/demo/{img}"
            if hardcoded in gitlab_ci:
                gitlab_ci = gitlab_ci.replace(
                    hardcoded,
                    f"localhost:5001/apm-repo/demo/{correct_compile_image}"
                )
                corrections.append(f"CI: Replaced hardcoded {img} with {correct_compile_image}")

    # -- Fix same-language outdated image versions --
    # LLM may generate older versions (e.g., golang:1.21-alpine instead of golang:1.22-alpine-git)
    if correct_compile_image and full_correct_image not in gitlab_ci:
        # Find all image references for this language family in CI
        lang_prefix = correct_compile_image.split(':')[0]  # e.g. "golang", "rust", "python"
        old_image_pattern = rf'(\${{NEXUS_PULL_REGISTRY}}/apm-repo/demo/)({_re.escape(lang_prefix)}:[^\s"\']+)'
        for m in _re.finditer(old_image_pattern, gitlab_ci):
            old_img = m.group(2)
            if old_img != correct_compile_image:
                gitlab_ci = gitlab_ci.replace(m.group(0), full_correct_image)
                corrections.append(f"CI: Upgraded {old_img} to {correct_compile_image}")
        # Also fix hardcoded versions
        old_hardcoded_pattern = rf'(localhost:5001/apm-repo/demo/)({_re.escape(lang_prefix)}:[^\s"\']+)'
        for m in _re.finditer(old_hardcoded_pattern, gitlab_ci):
            old_img = m.group(2)
            if old_img != correct_compile_image:
                gitlab_ci = gitlab_ci.replace(m.group(0), f"localhost:5001/apm-repo/demo/{correct_compile_image}")
                corrections.append(f"CI: Upgraded hardcoded {old_img} to {correct_compile_image}")

    # -- Fix compile commands if wrong --
    if correct_commands and lang == "rust":
        # Common wrong commands for Rust
        wrong_commands = {
            "mvn clean package": "cargo build --release",
            "mvn package": "cargo build --release",
            "npm install": "cargo build --release",
            "pip install": "cargo build --release",
            "go build": "cargo build --release",
        }
        for wrong_cmd, right_cmd in wrong_commands.items():
            if wrong_cmd in gitlab_ci and "cargo" not in gitlab_ci:
                gitlab_ci = gitlab_ci.replace(wrong_cmd, right_cmd, 1)
                corrections.append(f"CI: Replaced '{wrong_cmd}' with '{right_cmd}'")

    # -- Fix Dockerfile base image --
    if correct_dockerfile_image and dockerfile:
        nexus_dockerfile_prefix = "ai-nexus:5001/apm-repo/demo/"
        # Check if Dockerfile uses wrong base image
        for other_lang, img in LANGUAGE_DOCKERFILE_IMAGES.items():
            if other_lang != lang and img != correct_dockerfile_image:
                wrong_df_img = f"{nexus_dockerfile_prefix}{img}"
                correct_df_img = f"{nexus_dockerfile_prefix}{correct_dockerfile_image}"
                if wrong_df_img in dockerfile:
                    dockerfile = dockerfile.replace(wrong_df_img, correct_df_img)
                    corrections.append(f"Dockerfile: Replaced {img} with {correct_dockerfile_image}")

        # Fix same-language outdated Dockerfile images
        lang_prefix = correct_dockerfile_image.split(':')[0]
        for prefix_variant in [nexus_dockerfile_prefix, "${BASE_REGISTRY}/apm-repo/demo/"]:
            old_df_pattern = _re.compile(
                rf'({_re.escape(prefix_variant)})({_re.escape(lang_prefix)}:[^\s"\']+)'
            )
            for m in old_df_pattern.finditer(dockerfile):
                old_img = m.group(2)
                if old_img != correct_dockerfile_image:
                    dockerfile = dockerfile.replace(m.group(0), f"{prefix_variant}{correct_dockerfile_image}")
                    corrections.append(f"Dockerfile: Upgraded {old_img} to {correct_dockerfile_image}")

        # Fix Dockerfile that uses alpine/nginx for Rust (needs rust image)
        if lang == "rust" and "cargo" not in dockerfile:
            # Check if the Dockerfile doesn't have cargo -- likely wrong base image
            if "alpine" in dockerfile.lower() and "rustup" not in dockerfile.lower():
                # Complete rewrite for Rust Dockerfile
                dockerfile = f"""# Uses Nexus private registry - ai-nexus:5001
ARG BASE_REGISTRY=ai-nexus:5001
FROM ${{BASE_REGISTRY}}/apm-repo/demo/{correct_dockerfile_image} AS builder

WORKDIR /app

COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {{}}" > src/main.rs && cargo build --release && rm -rf src
COPY src/ ./src/

RUN cargo build --release

FROM ${{BASE_REGISTRY}}/apm-repo/demo/alpine:3.18

WORKDIR /app

COPY --from=builder /app/target/release/* .

EXPOSE 8080

CMD ["./app"]
"""
                corrections.append("Dockerfile: Complete rewrite for Rust (was using wrong base)")

    if corrections:
        print(f"[ImageValidator] Fixed {len(corrections)} image issues for {language}:")
        for c in corrections:
            print(f"  - {c}")

    return gitlab_ci, dockerfile, corrections


def _validate_and_fix_pipeline(generated: str, reference: Optional[str]) -> str:
    """
    Validate generated pipeline against guardrails and fix common issues.
    Ensures the pipeline follows the template structure from ChromaDB.
    """
    if not generated:
        return generated

    # GUARDRAIL 1: Check for required 8 stages
    required_stages = ['compile', 'build', 'test', 'sast', 'quality', 'security', 'push', 'notify']
    stages_pattern = r'stages:\s*\n((?:\s*-\s*\w+\s*\n?)+)'
    stages_match = re.search(stages_pattern, generated)

    if stages_match:
        found_stages = re.findall(r'-\s*(\w+)', stages_match.group(1))
        missing_stages = [s for s in required_stages if s not in found_stages]
        if missing_stages:
            print(f"WARNING: Pipeline missing stages: {missing_stages}")
            # Fix by inserting correct stages block
            correct_stages = "stages:\n" + "\n".join([f"  - {s}" for s in required_stages])
            generated = re.sub(stages_pattern, correct_stages + "\n", generated)

    # GUARDRAIL 2: Replace localhost with DNS names (except for NEXUS_PULL_REGISTRY which MUST stay localhost:5001)
    # NOTE: Do NOT replace localhost:5001 globally - NEXUS_PULL_REGISTRY must use localhost:5001
    # because Docker Desktop needs to pull images from localhost, not ai-nexus (which is only resolvable inside containers)
    replacements = [
        # (r'localhost:5001', 'ai-nexus:5001'),  # REMOVED - breaks NEXUS_PULL_REGISTRY
        (r'localhost:8081', 'ai-nexus:8081'),
        (r'localhost:9000', 'ai-sonarqube:9000'),
        (r'localhost:9002', 'ai-sonarqube:9000'),
        (r'localhost:8088', 'ai-splunk:8088'),
        (r'localhost:8929', 'gitlab-server'),
        (r'localhost:11434', 'ollama:11434'),
        # (r'127\.0\.0\.1', 'ai-nexus'),  # REMOVED - too broad, can break things
    ]
    for pattern, replacement in replacements:
        generated = re.sub(pattern, replacement, generated)

    # GUARDRAIL 2.5: Fix NEXUS_PULL_REGISTRY value (MUST be localhost:5001, not ai-nexus:5001)
    # This fixes cases where the AI model incorrectly uses ai-nexus:5001 for NEXUS_PULL_REGISTRY
    generated = re.sub(
        r'NEXUS_PULL_REGISTRY:\s*["\']?ai-nexus:5001["\']?',
        'NEXUS_PULL_REGISTRY: "localhost:5001"',
        generated
    )

    # GUARDRAIL 2.6: Clean up malformed job names (AI sometimes generates garbage in job names)
    # Fix lines like: "build_image: ${NEXUS_PULL_REGISTRY}/apm-repo/demo/ build" -> "build_image:"
    # First, normalize line endings
    generated = generated.replace('\r\n', '\n').replace('\r', '\n')

    # Pattern to catch: job_name: ${...}/path garbage
    malformed_patterns = [
        # Match any job name followed by ${NEXUS_PULL_REGISTRY}
        (r'^(\w+):\s*\$\{NEXUS_PULL_REGISTRY\}/apm-repo/demo/\s+\w+\s*$', r'\1:'),
        # Match job_image patterns specifically
        (r'^(\w+_image):\s*\$\{NEXUS_PULL_REGISTRY\}[^\n]+$', r'\1:'),
        # Match any job: ${...} pattern that looks malformed
        (r'^(\w+):\s*\$\{[A-Z_]+\}/[^\n]*\s+(build|test|compile)\s*$', r'\1:'),
    ]
    for pattern, replacement in malformed_patterns:
        generated = re.sub(pattern, replacement, generated, flags=re.MULTILINE)

    # GUARDRAIL 2.7: Fix malformed image declarations (duplicate registry paths)
    generated = generated.replace(
        '${NEXUS_PULL_REGISTRY}/apm-repo/demo/ ${NEXUS_PULL_REGISTRY}/apm-repo/demo/',
        '${NEXUS_PULL_REGISTRY}/apm-repo/demo/'
    )

    # Fix 2: Also try with regex for any variations
    malformed_image_patterns = [
        (r'\$\{NEXUS_PULL_REGISTRY\}/apm-repo/demo/\s+\$\{NEXUS_PULL_REGISTRY\}/apm-repo/demo/', '${NEXUS_PULL_REGISTRY}/apm-repo/demo/'),
        (r'\$\{NEXUS_REGISTRY\}/apm-repo/demo/\s+\$\{NEXUS_REGISTRY\}/apm-repo/demo/', '${NEXUS_REGISTRY}/apm-repo/demo/'),
    ]
    for pattern, replacement in malformed_image_patterns:
        generated = re.sub(pattern, replacement, generated)

    # GUARDRAIL 3: Ensure all jobs have tags: [docker]
    # Find jobs without tags and add them
    job_pattern = r'^(\w+):\s*\n((?:(?!^\w+:).*\n)*)'

    def add_tags_if_missing(match):
        job_name = match.group(1)
        job_content = match.group(2)
        # Skip if it's stages, variables, or already has tags
        if job_name in ['stages', 'variables', 'default', 'workflow', 'include']:
            return match.group(0)
        if 'tags:' not in job_content:
            # Add tags after the first line
            lines = job_content.split('\n')
            if lines:
                # Find the indentation level
                indent = '  '
                for line in lines:
                    if line.strip():
                        indent = ' ' * (len(line) - len(line.lstrip()))
                        break
                job_content = f"{indent}tags: [docker]\n{job_content}"
        return f"{job_name}:\n{job_content}"

    generated = re.sub(job_pattern, add_tags_if_missing, generated, flags=re.MULTILINE)

    # GUARDRAIL 4: Ensure Nexus registry uses correct path
    # IMPORTANT: Use [^\S\n]* instead of \s* to avoid matching across newlines
    # This prevents merging multi-line image blocks incorrectly
    # Only match images that are on the same line (not block format like image:\n  name:)
    generated = re.sub(
        r'image:[ \t]*(["\']?)(?!\$|ai-nexus)([a-zA-Z][a-zA-Z0-9._-]*[:/])',
        r'image: \1${NEXUS_PULL_REGISTRY}/apm-repo/demo/',
        generated
    )

    # GUARDRAIL 5: Ensure variables block has required entries
    # IMPORTANT: NEXUS_PULL_REGISTRY must be localhost:5001 (for Docker Desktop to pull images)
    # NEXUS_INTERNAL_REGISTRY should be ai-nexus:5001 (for Kaniko inside containers)
    required_vars = {
        'NEXUS_REGISTRY': '"localhost:5001"',
        'NEXUS_PULL_REGISTRY': '"localhost:5001"',
        'NEXUS_INTERNAL_REGISTRY': '"ai-nexus:5001"',
        'SONARQUBE_URL': '"http://ai-sonarqube:9000"',
        'SPLUNK_HEC_URL': '"http://ai-splunk:8088"'
    }

    for var_name, var_value in required_vars.items():
        if var_name not in generated:
            # Add to variables block
            var_line = f"  {var_name}: {var_value}\n"
            generated = re.sub(
                r'(variables:\s*\n)',
                r'\1' + var_line,
                generated
            )

    # GUARDRAIL 6: Ensure notify stage has success and failure jobs
    if 'notify_success' not in generated and 'notify' in generated:
        print("WARNING: Pipeline missing notify_success job")
    if 'notify_failure' not in generated and 'notify' in generated:
        print("WARNING: Pipeline missing notify_failure job")

    # GUARDRAIL 7: Fix Kaniko auth echo command - escape quotes for valid YAML
    # The AI model often generates unescaped JSON which breaks YAML parsing:
    #   echo "{"auths":{"${NEXUS_INTERNAL_REGISTRY}":...}}" (INVALID)
    # Must be:
    #   echo "{\"auths\":{\"${NEXUS_INTERNAL_REGISTRY}\":...}}" (VALID)

    # Pattern to match malformed Kaniko config echo (unescaped JSON)
    kaniko_auth_pattern = r'echo\s+"(\{)("?)auths("?)(\}?)\s*:\s*(\{)("?)\$\{NEXUS_INTERNAL_REGISTRY\}("?)(\}?)\s*:\s*(\{)("?)username("?)(\}?)\s*:\s*("?)\$\{NEXUS_USERNAME\}("?)\s*,\s*("?)password("?)(\}?)\s*:\s*("?)\$\{NEXUS_PASSWORD\}("?)(\}*)"\s*>\s*/kaniko/\.docker/config\.json'

    # Direct replacement for the common malformed pattern
    generated = generated.replace(
        'echo "{"auths":{"${NEXUS_INTERNAL_REGISTRY}":{"username":"${NEXUS_USERNAME}","password":"${NEXUS_PASSWORD}"}}}" > /kaniko/.docker/config.json',
        'echo "{\\"auths\\":{\\"${NEXUS_INTERNAL_REGISTRY}\\":{\\"username\\":\\"${NEXUS_USERNAME}\\",\\"password\\":\\"${NEXUS_PASSWORD}\\"}}}" > /kaniko/.docker/config.json'
    )

    # Also fix variant with NEXUS_REGISTRY instead of NEXUS_INTERNAL_REGISTRY
    generated = generated.replace(
        'echo "{"auths":{"${NEXUS_REGISTRY}":{"username":"${NEXUS_USERNAME}","password":"${NEXUS_PASSWORD}"}}}" > /kaniko/.docker/config.json',
        'echo "{\\"auths\\":{\\"${NEXUS_INTERNAL_REGISTRY}\\":{\\"username\\":\\"${NEXUS_USERNAME}\\",\\"password\\":\\"${NEXUS_PASSWORD}\\"}}}" > /kaniko/.docker/config.json'
    )

    # GUARDRAIL 8: Fix curl commands with headers - colons in strings break YAML parsing
    # Any curl command with -H header or -d JSON payload needs to be wrapped in YAML quotes
    # because headers contain colons (e.g., "Content-Type: application/json")
    # In YAML single-quoted strings, single quotes are escaped by doubling them ('')

    lines = generated.split('\n')
    fixed_lines = []
    for line in lines:
        stripped = line.lstrip()
        # Check if this is a curl command with headers (-H) or JSON data (-d)
        # These typically have colons that YAML tries to interpret as mappings
        if stripped.startswith('- curl') and ('-H ' in line or '-d ' in line):
            # Get the indentation
            indent = line[:len(line) - len(stripped)]
            # Remove the leading "- " and wrap in single quotes
            cmd = stripped[2:]  # Remove "- "
            # In YAML single-quoted strings, escape single quotes by doubling them
            cmd_escaped = cmd.replace("'", "''")
            # Wrap in single quotes for YAML
            fixed_line = f"{indent}- '{cmd_escaped}'"
            fixed_lines.append(fixed_line)
        else:
            fixed_lines.append(line)
    generated = '\n'.join(fixed_lines)

    # Also fix the common single-quoted JSON patterns that break YAML
    generated = generated.replace(
        "-d '{\"event\": \"Pipeline succeeded\", \"source\": \"${CI_PROJECT_NAME}\"}'",
        '-d "{\\"event\\": \\"Pipeline succeeded\\", \\"source\\": \\"${CI_PROJECT_NAME}\\"}"'
    )
    generated = generated.replace(
        "-d '{\"event\": \"Pipeline failed\", \"source\": \"${CI_PROJECT_NAME}\"}'",
        '-d "{\\"event\\": \\"Pipeline failed\\", \\"source\\": \\"${CI_PROJECT_NAME}\\"}"'
    )

    # GUARDRAIL 9: Fix allow_failure/when/artifacts keys concatenated onto script lines
    # This catches data quality issues where YAML keys get merged onto the previous line:
    #   - /kaniko/executor ...  allow_failure: true  (WRONG)
    # Should be:
    #   - /kaniko/executor ...
    #   allow_failure: true                          (CORRECT)
    yaml_keys_on_script = re.compile(
        r'^(\s+- .+?) {2,}(allow_failure:\s*true|when:\s*\w+|artifacts:)$',
        re.MULTILINE
    )
    generated = yaml_keys_on_script.sub(r'\1\n  \2', generated)

    # GUARDRAIL 10: Ensure all jobs have script: field
    # GitLab requires jobs to have script:, run:, or trigger: keyword
    # Fix notify_failure and notify_success if they're missing script
    # Note: 're' module is imported at file top level

    # Pattern to find job definitions that might be missing script
    lines = generated.split('\n')
    fixed_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        fixed_lines.append(line)

        # Check if this is a notify job definition
        if line.strip().startswith('notify_failure:') or line.strip().startswith('notify_success:'):
            job_name = line.strip().rstrip(':')
            # Look ahead to check if script: exists before next job or end
            has_script = False
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                if next_line.strip() and not next_line.startswith(' ') and not next_line.startswith('\t'):
                    # Found next job definition or end of section
                    break
                if 'script:' in next_line or 'script :' in next_line:
                    has_script = True
                    break
                j += 1

            # If no script found, add one after collecting job properties
            if not has_script:
                # Find where to insert script (after other properties like when:, allow_failure:)
                insert_idx = len(fixed_lines)
                k = i + 1
                while k < len(lines) and (lines[k].startswith('  ') or lines[k].strip() == ''):
                    fixed_lines.append(lines[k])
                    k += 1
                    i += 1
                # Add script before we continue
                if 'failure' in job_name:
                    fixed_lines.insert(-1 if fixed_lines[-1].strip() else len(fixed_lines), '  script:\n    - echo "Pipeline failed"')
                else:
                    fixed_lines.insert(-1 if fixed_lines[-1].strip() else len(fixed_lines), '  script:\n    - echo "Pipeline succeeded"')
                print(f"[Guardrail 9] Added missing script to {job_name}")
        i += 1

    generated = '\n'.join(fixed_lines)

    return generated


def _validate_and_fix_dockerfile(dockerfile: str, language: str) -> str:
    """
    Validate and fix Dockerfile to ensure all images come from Nexus private registry.
    NEVER allow public registry images (docker.io, gcr.io, quay.io, etc.)
    """
    if not dockerfile:
        return dockerfile

    # Map of public images to Nexus equivalents
    nexus_registry = "ai-nexus:5001/apm-repo/demo"
    image_mappings = {
        # Java
        'openjdk': f'{nexus_registry}/amazoncorretto:17-alpine-jdk',
        'amazoncorretto': f'{nexus_registry}/amazoncorretto:17-alpine-jdk',
        'eclipse-temurin': f'{nexus_registry}/amazoncorretto:17-alpine-jdk',
        'maven': f'{nexus_registry}/maven:3.9-eclipse-temurin-17',
        'gradle': f'{nexus_registry}/gradle:8-jdk17-alpine',
        # Python
        'python:3': f'{nexus_registry}/python:3.11-slim',
        'python:latest': f'{nexus_registry}/python:3.11-slim',
        'python': f'{nexus_registry}/python:3.11-slim',
        # Node.js
        'node:18': f'{nexus_registry}/node:18-alpine',
        'node:20': f'{nexus_registry}/node:20-alpine',
        'node:latest': f'{nexus_registry}/node:18-alpine',
        'node': f'{nexus_registry}/node:18-alpine',
        # Go (must include git for go mod download)
        'golang:1.21': f'{nexus_registry}/golang:1.22-alpine-git',
        'golang:1.22': f'{nexus_registry}/golang:1.22-alpine-git',
        'golang:latest': f'{nexus_registry}/golang:1.22-alpine-git',
        'golang': f'{nexus_registry}/golang:1.22-alpine-git',
        # Base images
        'alpine:3': f'{nexus_registry}/alpine:3.18',
        'alpine:latest': f'{nexus_registry}/alpine:3.18',
        'alpine': f'{nexus_registry}/alpine:3.18',
        'nginx:alpine': f'{nexus_registry}/nginx:alpine',
        'nginx:latest': f'{nexus_registry}/nginx:alpine',
        'nginx': f'{nexus_registry}/nginx:alpine',
        'ubuntu': f'{nexus_registry}/ubuntu:22.04',
        'debian': f'{nexus_registry}/debian:bookworm-slim',
    }

    # GUARDRAIL 1: Ensure ARG BASE_REGISTRY exists at the top
    if 'ARG BASE_REGISTRY' not in dockerfile:
        dockerfile = f"ARG BASE_REGISTRY={nexus_registry.split('/')[0]}\n" + dockerfile
        print("[Dockerfile] Added ARG BASE_REGISTRY")

    # GUARDRAIL 2: Replace public registry references in FROM statements
    # Pattern to match FROM statements with various formats
    from_pattern = r'^FROM\s+(?!.*ai-nexus)(?!.*\$\{)([^\s]+)'

    def replace_from(match):
        original_image = match.group(1)
        print(f"[Dockerfile] Found public image: {original_image}")

        # Check if it's already using Nexus
        if 'ai-nexus' in original_image or '${BASE_REGISTRY}' in original_image:
            return match.group(0)

        # Remove docker.io/ prefix if present
        clean_image = original_image.replace('docker.io/', '').replace('library/', '')

        # Try to find a mapping
        for public, nexus in image_mappings.items():
            if clean_image.startswith(public):
                print(f"[Dockerfile] Replacing {original_image} -> ${{BASE_REGISTRY}}/{nexus.split('/', 1)[1] if '/' in nexus else nexus}")
                return f"FROM ${{BASE_REGISTRY}}/{nexus.split(nexus_registry + '/')[1] if nexus_registry in nexus else clean_image}"

        # Default: prepend Nexus registry path
        print(f"[Dockerfile] Converting {original_image} to Nexus format")
        return f"FROM ${{BASE_REGISTRY}}/{clean_image}"

    dockerfile = re.sub(from_pattern, replace_from, dockerfile, flags=re.MULTILINE)

    # GUARDRAIL 3: Replace any remaining public registry URLs
    public_registries = [
        (r'docker\.io/', '${BASE_REGISTRY}/'),
        (r'gcr\.io/', '${BASE_REGISTRY}/'),
        (r'ghcr\.io/', '${BASE_REGISTRY}/'),
        (r'quay\.io/', '${BASE_REGISTRY}/'),
        (r'registry\.hub\.docker\.com/', '${BASE_REGISTRY}/'),
        (r'mcr\.microsoft\.com/', '${BASE_REGISTRY}/'),
    ]

    for pattern, replacement in public_registries:
        if re.search(pattern, dockerfile):
            print(f"[Dockerfile] Replacing public registry pattern: {pattern}")
            dockerfile = re.sub(pattern, replacement, dockerfile)

    # GUARDRAIL 4: Ensure multi-stage builds use ${BASE_REGISTRY}
    # Fix any FROM statements that don't use the variable
    dockerfile = re.sub(
        r'^FROM\s+(?!\$\{BASE_REGISTRY\})(?!.*ai-nexus)([a-zA-Z0-9\-_]+[:/][^\s]+)',
        r'FROM ${BASE_REGISTRY}/\1',
        dockerfile,
        flags=re.MULTILINE
    )

    # GUARDRAIL 5: Add comment about Nexus requirement
    if '# Uses Nexus private registry' not in dockerfile:
        dockerfile = "# Uses Nexus private registry - ai-nexus:5001\n" + dockerfile

    return dockerfile


def _extract_code_block(text: str, block_type: str) -> Optional[str]:
    """Extract code block from markdown-style response"""
    patterns = [
        rf'```{block_type}\n(.*?)```',
        rf'```{block_type}\s*\n(.*?)```',
        rf'```yaml\n(.*?)```' if block_type == 'gitlab-ci' else rf'```dockerfile\n(.*?)```'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_yaml_content(text: str) -> Optional[str]:
    """Extract YAML content using various patterns"""
    # Look for stages: keyword which indicates gitlab-ci
    match = re.search(r'(stages:.*?)(?=```|$)', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _extract_dockerfile_content(text: str) -> Optional[str]:
    """Extract Dockerfile content"""
    match = re.search(r'(FROM\s+\S+.*?)(?=```|$)', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None
