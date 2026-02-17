"""
Image Seeder for GitHub Actions Workflows

Ensures all Docker images referenced in a generated GitHub Actions workflow
exist in the Nexus registry. If an image is missing, it is copied
from DockerHub into Nexus via `skopeo copy`.

Mirrors the Jenkins image_seeder.py adapted for GitHub Actions YAML syntax.
"""
import re
from typing import List, Dict

from app.config import settings

# Reuse core seeding infrastructure from GitLab image seeder
from app.services.pipeline.image_seeder import (
    _nexus_image_name,
    _dockerhub_ref,
    _nexus_ref,
    _check_image_exists,
    _seed_image,
    SKIP_PATTERNS,
    NEXUS_REGISTRY,
    NEXUS_REPO_PATH,
)


def extract_workflow_images(workflow: str) -> List[str]:
    """
    Parse a GitHub Actions workflow YAML and extract all Docker image references.
    Returns a list of unique bare image:tag names as stored in Nexus.

    Handles GitHub Actions patterns:
    - container: image: ai-nexus:5001/apm-repo/demo/maven:3.9-eclipse-temurin-17
    - uses: docker://image:tag
    - ${{ env.NEXUS_REGISTRY }}/apm-repo/demo/image:tag
    - run: docker build / docker pull / docker run references
    """
    images = set()

    # Pattern 1: container image or image: fields in YAML
    image_patterns = [
        re.compile(r'image:\s*["\']?([^\s"\'#]+)', re.MULTILINE),
        re.compile(r'container:\s*["\']?([^\s"\'#]+)', re.MULTILINE),
    ]

    for pattern in image_patterns:
        for match in pattern.finditer(workflow):
            raw = match.group(1).strip()
            if raw.startswith('$') and 'NEXUS' not in raw:
                continue
            images.add(raw)

    # Pattern 2: docker:// action references
    docker_uses_pattern = re.compile(r'uses:\s*docker://([^\s"\']+)', re.MULTILINE)
    for match in docker_uses_pattern.finditer(workflow):
        images.add(match.group(1).strip())

    # Pattern 3: docker pull/run commands
    docker_cmd_pattern = re.compile(r'docker\s+(?:pull|run|inspect)\s+["\']?([^\s"\'|&;]+)', re.MULTILINE)
    for match in docker_cmd_pattern.finditer(workflow):
        raw = match.group(1).strip()
        if raw.startswith('-') or raw.startswith('$'):
            continue
        images.add(raw)

    # Normalize: strip the Nexus prefix to get bare image name
    bare_images = set()
    for img in images:
        # Remove GitHub Actions expression wrapper
        img = re.sub(r'\$\{\{\s*env\.[A-Z_]+\s*\}\}/', '', img)
        # Remove variable-based prefix
        img = re.sub(r'\$\{[^}]+\}/', '', img)
        img = re.sub(r'\$[A-Z_]+/', '', img)
        # Remove literal Nexus prefix
        img = re.sub(r'ai-nexus:\d+/apm-repo/demo/', '', img)
        img = re.sub(r'localhost:\d+/apm-repo/demo/', '', img)
        # Remove bare repo path prefix
        img = re.sub(r'^apm-repo/demo/', '', img)
        # Remove any remaining registry prefix
        img = re.sub(r'^[a-zA-Z0-9._-]+:\d+/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+/', '', img)
        # Skip variable-only references
        if re.match(r'^\$', img):
            continue
        if img and ':' not in img:
            img += ':latest'
        if img:
            bare_images.add(img)

    return list(bare_images)


async def ensure_images_in_nexus(workflow: str) -> Dict:
    """
    Main entry point. Extract all image references from a GitHub Actions workflow,
    check each one in Nexus, and seed any that are missing.

    Returns {"seeded": [...], "already_exists": [...], "failed": [...], "skipped": [...]}.
    Best-effort: failures do NOT block workflow generation.
    """
    result = {"seeded": [], "already_exists": [], "failed": [], "skipped": []}

    bare_images = extract_workflow_images(workflow)
    if not bare_images:
        return result

    print(f"[GitHub ImageSeeder] Found {len(bare_images)} unique images: {bare_images}")

    for img in bare_images:
        name_part = img.split(':')[0]
        if any(skip in name_part for skip in SKIP_PATTERNS):
            result["skipped"].append(img)
            continue

        exists = await _check_image_exists(img)
        if exists:
            result["already_exists"].append(img)
        else:
            ok = await _seed_image(img)
            if ok:
                result["seeded"].append(img)
            else:
                result["failed"].append(img)

    summary_parts = []
    if result["seeded"]:
        summary_parts.append(f"seeded {len(result['seeded'])}")
    if result["already_exists"]:
        summary_parts.append(f"{len(result['already_exists'])} exist")
    if result["failed"]:
        summary_parts.append(f"{len(result['failed'])} failed")
    if result["skipped"]:
        summary_parts.append(f"{len(result['skipped'])} skipped")
    print(f"[GitHub ImageSeeder] Done: {', '.join(summary_parts)}")

    return result
