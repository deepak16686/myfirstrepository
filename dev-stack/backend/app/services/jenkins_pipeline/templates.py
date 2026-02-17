"""
ChromaDB template operations for Jenkins pipelines.

Handles retrieving reference Jenkinsfiles and best-performing templates.
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
    framework: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Get the best performing template from successful pipelines"""
    chromadb_url = settings.chromadb_url
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            coll_uuid = await _resolve_collection_uuid(client, SUCCESSFUL_PIPELINES_COLLECTION)
            if not coll_uuid:
                return None

            where_filter = {"language": language}
            if framework:
                where_filter = {
                    "$and": [
                        {"language": language},
                        {"framework": framework}
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

            if response.status_code == 200:
                data = response.json()
                documents = data.get("documents", [])
                metadatas = data.get("metadatas", [])

                if documents:
                    # Sort by success_count and duration
                    best_idx = 0
                    best_score = 0
                    for i, meta in enumerate(metadatas):
                        score = meta.get("success_count", 0) * 100 - meta.get("duration", 0)
                        if score > best_score:
                            best_score = score
                            best_idx = i

                    doc = documents[best_idx]
                    # Try to parse as structured document
                    try:
                        import yaml
                        parsed = yaml.safe_load(doc)
                        return {
                            "jenkinsfile": parsed.get("jenkinsfile", ""),
                            "dockerfile": parsed.get("dockerfile", ""),
                            "source": "chromadb-successful"
                        }
                    except Exception:
                        # Return raw document as jenkinsfile
                        return {
                            "jenkinsfile": doc,
                            "dockerfile": "",
                            "source": "chromadb-successful"
                        }

    except Exception as e:
        print(f"[ChromaDB] Error getting best template: {e}")

    return None
