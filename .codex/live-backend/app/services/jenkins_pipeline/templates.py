"""
File: templates.py
Purpose: Manages ChromaDB-backed template operations for Jenkins pipelines: retrieving
    reference Jenkinsfiles for LLM prompts, fetching the best-performing template from
    successful pipelines (ranked by success count and build duration), ensuring the Learn
    stage curl exists in generated pipelines, and resolving ChromaDB collection name-to-UUID
    mappings required by the v2 API.
When Used: Called during pipeline generation to check if a proven successful template exists
    in ChromaDB (priority 1 in the generation chain) and to fetch reference templates that
    guide LLM output. The _ensure_learn_stage() function is applied to every generated
    Jenkinsfile to guarantee the RL feedback curl is present.
Why Created: Extracted from the generator to separate ChromaDB query logic and template
    management from the core generation orchestration, keeping template retrieval, ranking,
    and post-processing in a focused module.
"""
import re
import httpx
from typing import Dict, Any, Optional

from app.config import settings
from app.services.jenkins_pipeline.constants import (
    FEEDBACK_COLLECTION,
    TEMPLATES_COLLECTION,
    SUCCESSFUL_PIPELINES_COLLECTION,
)

# Cache collection name -> UUID mappings
_collection_uuid_cache: Dict[str, str] = {}


def _normalize_version(version: Optional[str]) -> str:
    if not version:
        return ""
    value = str(version).strip().lower()
    value = re.sub(r"^(java|jdk|python|py|node|go|golang|ruby|php|dotnet|rust)[-_]?", "", value)
    return value


def _versioned_framework(framework: Optional[str], language: str, version: Optional[str]) -> Optional[str]:
    version_value = _normalize_version(version)
    if not framework or not version_value:
        return None
    framework_value = framework.lower()
    language_value = language.lower()
    if re.search(rf"(?:^|[-_]){re.escape(language_value)}{re.escape(version_value)}$", framework_value):
        return framework
    return f"{framework}-{language_value}{version_value}"


def _candidate_frameworks(language: str, framework: Optional[str], version: Optional[str]) -> list[str]:
    candidates: list[str] = []
    versioned = _versioned_framework(framework, language, version)
    if versioned:
        candidates.append(versioned)
    if framework:
        candidates.append(framework)
    return list(dict.fromkeys(candidates))


async def _resolve_collection_uuid(client: httpx.AsyncClient, name: str) -> Optional[str]:
    """Resolve ChromaDB collection name to UUID (v2 API requires UUIDs)."""
    if name in _collection_uuid_cache:
        return _collection_uuid_cache[name]

    chromadb_url = settings.chromadb_url
    resp = await client.get(
        f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
    )
    if resp.status_code == 200:
        for coll in resp.json():
            if coll.get("name") == name:
                uuid = coll["id"]
                _collection_uuid_cache[name] = uuid
                return uuid
    return None


def _ensure_learn_stage(jenkinsfile: str) -> str:
    """Ensure the post block has the learn-record curl call.

    Unlike YAML-based pipelines, Jenkinsfile is Groovy so we use
    text-based checks rather than YAML parsing.
    """
    if not jenkinsfile:
        return jenkinsfile

    # Check if learn/record URL already exists
    if 'jenkins-pipeline/learn/record' in jenkinsfile:
        return jenkinsfile

    # Check if post { success { block exists
    if 'post {' not in jenkinsfile and 'post{' not in jenkinsfile:
        return jenkinsfile

    # Find the success block inside post and inject learn curl
    learn_curl = '''            sh """
                curl -s -X POST "${DEVOPS_BACKEND_URL}/api/v1/jenkins-pipeline/learn/record" \\
                  -H "Content-Type: application/json" \\
                  -d '{"job_name": "${JOB_NAME}", "build_number": ${BUILD_NUMBER}, "status": "success"}' \\
                  && echo "SUCCESS: Configuration recorded for RL"
            """'''

    # Try to inject after the first sh command in post success block
    # Look for pattern: success { ... sh "..." (splunk notify)
    # and add learn curl after it
    success_pattern = re.compile(r'(success\s*\{[^}]*?)((\s*\}\s*\n\s*failure))', re.DOTALL)
    match = success_pattern.search(jenkinsfile)
    if match:
        jenkinsfile = (
            jenkinsfile[:match.end(1)] +
            '\n' + learn_curl + '\n        ' +
            jenkinsfile[match.start(2):]
        )

    return jenkinsfile


async def get_reference_jenkinsfile(
    language: str,
    framework: Optional[str] = None
) -> Optional[str]:
    """Get reference Jenkinsfile from ChromaDB"""
    chromadb_url = settings.chromadb_url
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            coll_uuid = await _resolve_collection_uuid(client, TEMPLATES_COLLECTION)
            if not coll_uuid:
                return None

            # First try exact match with language + framework
            if framework:
                response = await client.post(
                    f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{coll_uuid}/get",
                    json={
                        "where": {
                            "$and": [
                                {"language": language},
                                {"framework": framework}
                            ]
                        },
                        "limit": 1,
                        "include": ["documents", "metadatas"]
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if data.get("documents"):
                        return data["documents"][0]

            # Try language-only match
            response = await client.post(
                f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{coll_uuid}/get",
                json={
                    "where": {"language": language},
                    "limit": 1,
                    "include": ["documents", "metadatas"]
                }
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("documents"):
                    return data["documents"][0]

    except Exception as e:
        print(f"[ChromaDB] Error getting reference Jenkinsfile: {e}")

    return None


async def get_best_template_files(
    language: str,
    framework: Optional[str] = None,
    version: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    """Get the best performing template from successful pipelines"""
    chromadb_url = settings.chromadb_url
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            coll_uuid = await _resolve_collection_uuid(client, SUCCESSFUL_PIPELINES_COLLECTION)
            if not coll_uuid:
                return None

            candidates = _candidate_frameworks(language, framework, version) or [None]
            for candidate_framework in candidates:
                where_filter = {"language": language}
                if candidate_framework:
                    where_filter = {
                        "$and": [
                            {"language": language},
                            {"framework": candidate_framework}
                        ]
                    }

                response = await client.post(
                    f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{coll_uuid}/get",
                    json={
                        "where": where_filter,
                        "limit": 10,
                        "include": ["documents", "metadatas"]
                    }
                )
                if response.status_code != 200:
                    continue
                data = response.json()
                documents = data.get("documents", [])
                metadatas = data.get("metadatas", [])

                if documents:
                    # Prefer entries that actually parse into a Jenkinsfile.
                    # Scoring ties ignored when a candidate yields no content.
                    best_idx = -1
                    best_score = float("-inf")
                    requested_version = _normalize_version(version)
                    for i, meta in enumerate(metadatas):
                        meta_version = _normalize_version(
                            meta.get("java_version") or meta.get("python_version")
                            or meta.get("language_version") or meta.get("version")
                        )
                        score = meta.get("success_count", 0) * 100 - meta.get("duration", 0)
                        if requested_version and meta_version == requested_version:
                            score += 10000
                        if score > best_score:
                            best_score = score
                            best_idx = i
                    if best_idx < 0:
                        best_idx = 0

                    doc = documents[best_idx]
                    # Extract Jenkinsfile and Dockerfile from Markdown format.
                    # Accept groovy, plain, or unlabeled fences (seed data uses plain ```).
                    jenkinsfile = ""
                    dockerfile = ""
                    groovy_match = re.search(
                        r'```(?:groovy|Jenkinsfile|jenkinsfile)?\s*\n(pipeline\s*\{.*?)\n\s*```',
                        doc, re.DOTALL
                    )
                    if groovy_match:
                        jenkinsfile = groovy_match.group(1).strip()

                    # Extract content between ```dockerfile ... ``` fences
                    docker_match = re.search(
                        r'```dockerfile\s*\n(.*?)\n\s*```',
                        doc, re.DOTALL
                    )
                    if docker_match:
                        dockerfile = docker_match.group(1).strip()

                    # Fallback: try YAML parse for non-markdown format
                    if not jenkinsfile:
                        try:
                            import yaml
                            parsed = yaml.safe_load(doc)
                            if isinstance(parsed, dict):
                                jenkinsfile = parsed.get("jenkinsfile", "")
                                dockerfile = parsed.get("dockerfile", "")
                        except Exception:
                            pass

                    if jenkinsfile:
                        return {
                            "jenkinsfile": jenkinsfile,
                            "dockerfile": dockerfile,
                            "source": "chromadb-successful",
                            "template_framework": candidate_framework or framework or "",
                            "version": version or ""
                        }

    except Exception as e:
        print(f"[ChromaDB] Error getting best template: {e}")

    return None
