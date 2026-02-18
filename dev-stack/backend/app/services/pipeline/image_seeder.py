"""
File: image_seeder.py
Purpose: Ensures all Docker images referenced in a generated .gitlab-ci.yml exist in the
    private Nexus registry. Parses image references from the pipeline YAML, checks each one
    against the Nexus search API, and copies any missing images from DockerHub via skopeo.
When Used: Called automatically after pipeline generation and validation (but before committing
    to GitLab) to prevent pipeline jobs from failing with "manifest unknown" errors due to
    missing images in Nexus. Also runs when proven templates are loaded from ChromaDB.
Why Created: Extracted as a standalone module because image seeding is a distinct infrastructure
    concern separate from pipeline generation or validation. It was added after observing that
    LLM-generated pipelines frequently referenced images not yet mirrored to Nexus, causing
    avoidable build failures.
"""
import asyncio
import re
import subprocess
from typing import List, Dict

from app.config import settings


# Nexus registry details (from container's perspective)
NEXUS_REGISTRY = "ai-nexus:5001"
NEXUS_REPO_PATH = "apm-repo/demo"
NEXUS_API_BASE = settings.nexus_url  # http://ai-nexus:8081


def extract_pipeline_images(gitlab_ci: str) -> List[str]:
    """
    Parse a .gitlab-ci.yml string and extract all Docker image references.
    Returns a list of unique bare image:tag names as stored in Nexus
    (e.g. ["golang:1.22-alpine", "kaniko-executor:debug", "curlimages-curl:latest"]).
    """
    images = set()

    # Pattern 1: `image: <registry>/<path>/<name>:<tag>` (single-line)
    # Pattern 2: `image:\n  name: <registry>/<path>/<name>:<tag>`
    patterns = [
        re.compile(r'^\s*image:\s*["\']?([^"\'\s#]+)["\']?\s*$', re.MULTILINE),
        re.compile(r'^\s*-?\s*name:\s*["\']?([^"\'\s#]+)["\']?\s*$', re.MULTILINE),
    ]

    for pattern in patterns:
        for match in pattern.finditer(gitlab_ci):
            raw = match.group(1).strip()
            # Skip pure variable references like $CI_REGISTRY_IMAGE (no path after)
            if re.match(r'^\$\{?[A-Z_]+\}?$', raw):
                continue
            images.add(raw)

    # Normalize: strip the Nexus prefix to get bare image name
    # e.g. "${NEXUS_PULL_REGISTRY}/apm-repo/demo/golang:1.22-alpine" → "golang:1.22-alpine"
    # e.g. "ai-nexus:5001/apm-repo/demo/golang:1.22-alpine" → "golang:1.22-alpine"
    bare_images = set()
    for img in images:
        # Remove variable-based prefix (e.g. ${NEXUS_PULL_REGISTRY}/)
        img = re.sub(r'\$\{[^}]+\}/', '', img)
        # Remove literal Nexus prefix (with or without host:port)
        img = re.sub(r'ai-nexus:\d+/apm-repo/demo/', '', img)
        img = re.sub(r'localhost:\d+/apm-repo/demo/', '', img)
        # Remove bare repo path prefix (after variable prefix was stripped)
        img = re.sub(r'^apm-repo/demo/', '', img)
        # Remove any remaining registry prefix that looks like host:port/repo/path/
        img = re.sub(r'^[a-zA-Z0-9._-]+:\d+/[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+/', '', img)
        if img and ':' not in img:
            img += ':latest'
        if img:
            bare_images.add(img)

    return list(bare_images)


def _nexus_image_name(bare_image: str) -> str:
    """
    Convert a bare image name to the Nexus storage path.
    DockerHub namespaced images have '/' replaced with '-':
      curlimages/curl:latest  → curlimages-curl
      sonarsource/sonar-scanner-cli:5 → sonarsource-sonar-scanner-cli
      golang:1.22-alpine → golang
    """
    name_part = bare_image.split(':')[0]
    return name_part.replace('/', '-')


# Nexus stores namespaced images with '-' instead of '/'.
# This maps the Nexus-style name prefix back to DockerHub namespace.
NEXUS_TO_DOCKERHUB = {
    "curlimages-curl": "curlimages/curl",
    "sonarsource-sonar-scanner-cli": "sonarsource/sonar-scanner-cli",
    "aquasec-trivy": "aquasec/trivy",
    "kaniko-executor": "gcr.io/kaniko-project/executor",
    "bitnami-git": "bitnami/git",
    "hadolint-hadolint": "hadolint/hadolint",
    "checkmarx-kics": "checkmarx/kics",
    "grafana-grafana": "grafana/grafana",
}


def _dockerhub_ref(bare_image: str) -> str:
    """
    Convert a bare image name to a full DockerHub reference for skopeo.
      golang:1.22-alpine → docker://docker.io/library/golang:1.22-alpine
      curlimages-curl:latest → docker://docker.io/curlimages/curl:latest
      gcr.io/kaniko-project/executor:debug → docker://gcr.io/kaniko-project/executor:debug
    """
    name_part = bare_image.split(':')[0]
    tag = bare_image.split(':')[1] if ':' in bare_image else 'latest'

    # Check the known Nexus-to-DockerHub mapping first
    if name_part in NEXUS_TO_DOCKERHUB:
        hub_name = NEXUS_TO_DOCKERHUB[name_part]
        # Some map to non-DockerHub registries (e.g. gcr.io)
        if '.' in hub_name.split('/')[0]:
            return f"docker://{hub_name}:{tag}"
        return f"docker://docker.io/{hub_name}:{tag}"

    # Already a full registry reference (gcr.io, quay.io, etc.)
    if '.' in name_part.split('/')[0]:
        return f"docker://{name_part}:{tag}"

    # Namespaced DockerHub image (e.g. curlimages/curl)
    if '/' in name_part:
        return f"docker://docker.io/{name_part}:{tag}"

    # Official library image (e.g. golang, python, node)
    return f"docker://docker.io/library/{name_part}:{tag}"


def _nexus_ref(bare_image: str) -> str:
    """
    Build the Nexus destination reference for skopeo.
      golang:1.22-alpine → docker://ai-nexus:5001/apm-repo/demo/golang:1.22-alpine
      curlimages/curl:latest → docker://ai-nexus:5001/apm-repo/demo/curlimages-curl:latest
    """
    nexus_name = _nexus_image_name(bare_image)
    tag = bare_image.split(':')[1] if ':' in bare_image else 'latest'
    return f"docker://{NEXUS_REGISTRY}/{NEXUS_REPO_PATH}/{nexus_name}:{tag}"


async def _check_image_exists(bare_image: str) -> bool:
    """Check if an image+tag exists in Nexus via the search API."""
    import httpx

    nexus_name = _nexus_image_name(bare_image)
    tag = bare_image.split(':')[1] if ':' in bare_image else 'latest'

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{NEXUS_API_BASE}/service/rest/v1/search",
                params={
                    "repository": "apm-repo",
                    "format": "docker",
                    "name": f"apm-repo/demo/{nexus_name}",
                    "version": tag,
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                return len(data.get("items", [])) > 0
    except Exception as e:
        print(f"[ImageSeeder] Nexus check failed for {bare_image}: {e}")
    return False


async def _seed_image(bare_image: str) -> bool:
    """Copy image from DockerHub to Nexus using skopeo."""
    src = _dockerhub_ref(bare_image)
    dst = _nexus_ref(bare_image)

    nexus_password = settings.nexus_password or ""
    cmd = [
        "skopeo", "copy",
        "--dest-tls-verify=false",
        "--src-tls-verify=false",
        f"--dest-creds=admin:{nexus_password}",
        src, dst,
    ]

    print(f"[ImageSeeder] Seeding: {src} → {dst}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode == 0:
            print(f"[ImageSeeder] OK: {bare_image}")
            return True
        else:
            print(f"[ImageSeeder] FAILED ({proc.returncode}): {bare_image}\n  stderr: {stderr.decode()[:500]}")
            return False
    except asyncio.TimeoutError:
        print(f"[ImageSeeder] TIMEOUT: {bare_image}")
        return False
    except Exception as e:
        print(f"[ImageSeeder] ERROR: {bare_image}: {e}")
        return False


# Images that should NOT be seeded (they live in special registries or are
# virtual references that don't need to exist in Nexus).
SKIP_PATTERNS = [
    "kaniko-executor",   # gcr.io/kaniko-project — already handled in Nexus
    "kaniko",            # already in Nexus
]


async def ensure_images_in_nexus(gitlab_ci: str) -> Dict:
    """
    Main entry point. Extract all image references from a pipeline YAML,
    check each one in Nexus, and seed any that are missing.

    Returns {"seeded": [...], "already_exists": [...], "failed": [...]}.
    Best-effort: failures do NOT block pipeline generation.
    """
    result = {"seeded": [], "already_exists": [], "failed": [], "skipped": []}

    bare_images = extract_pipeline_images(gitlab_ci)
    if not bare_images:
        return result

    print(f"[ImageSeeder] Found {len(bare_images)} unique images: {bare_images}")

    for img in bare_images:
        # Skip known images that don't need seeding
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
    print(f"[ImageSeeder] Done: {', '.join(summary_parts)}")

    return result
