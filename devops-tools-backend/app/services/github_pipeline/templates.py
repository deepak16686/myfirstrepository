"""
File: templates.py
Purpose: Manages ChromaDB template retrieval for GitHub Actions workflows. Resolves collection
    UUIDs for the ChromaDB v2 API, fetches reference workflows for LLM context, retrieves the
    best-performing proven template from the successful_pipelines collection, and ensures every
    workflow includes a correctly-formatted learn-record job (using wget, not curl).
When Used: Called during the Priority 1 check in generate_workflow_files() to look for a proven
    successful template in ChromaDB, and during LLM generation (Priority 3) to provide a reference
    workflow. The _ensure_learn_job() function is applied to every generated workflow before return.
Why Created: Extracted from the generator to isolate all ChromaDB query logic and the learn-job
    injection/fixup logic, which involves YAML parsing and the on:/true: boolean workaround.
"""
import re
import yaml
import httpx
from typing import Dict, Any, Optional

from app.config import settings


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
                coll_uuid = coll["id"]
                _collection_uuid_cache[name] = coll_uuid
                return coll_uuid
    return None


FEEDBACK_COLLECTION = "github_actions_feedback"
TEMPLATES_COLLECTION = "github_actions_templates"
SUCCESSFUL_PIPELINES_COLLECTION = "github_actions_successful_pipelines"


def _ensure_learn_job(workflow: str) -> str:
    """Ensure the learn-record job exists with the correct endpoint and uses wget (not curl)."""
    try:
        parsed = yaml.safe_load(workflow)
        if not parsed or 'jobs' not in parsed:
            return workflow

        jobs = parsed.get('jobs', {})

        # Always replace learn-record job — LLM may generate wrong endpoint or use curl
        # Determine needs list from all other jobs, excluding notify-failure
        # (notify-failure has if:failure() so it's skipped on success, which would skip learn-record)
        excluded = {'learn-record', 'notify-failure'}
        other_jobs = [j for j in jobs.keys() if j not in excluded]
        needs_list = other_jobs if other_jobs else ['compile']

        # Uses wget (not curl) — Gitea Actions runner is Alpine-based
        jobs['learn-record'] = {
            'runs-on': 'self-hosted',
            'needs': needs_list,
            'if': 'success()',
            'steps': [
                {
                    'name': 'Record Pipeline Success for RL',
                    'run': 'wget -q --no-check-certificate '
                           '--header="Content-Type: application/json" '
                           '--post-data=\'{"repo_url": "${{ github.server_url }}/${{ github.repository }}", '
                           '"github_token": "${{ secrets.GITHUB_TOKEN }}", '
                           '"branch": "${{ github.ref_name }}", '
                           '"run_id": ${{ github.run_id }}}\' '
                           '"${{ env.DEVOPS_BACKEND_URL }}/api/v1/github-pipeline/learn/record" '
                           '-O /dev/null && echo "SUCCESS: Configuration recorded for RL"'
                }
            ]
        }
        parsed['jobs'] = jobs
        output = yaml.dump(parsed, default_flow_style=False, sort_keys=False)
        # Fix YAML boolean issue: yaml.dump converts `on:` key to `true:`
        output = output.replace('\ntrue:', '\non:', 1)
        if output.startswith('true:'):
            output = 'on:' + output[5:]
        return output

    except Exception as e:
        print(f"[Learn Job] Error adding learn job: {e}")
        return workflow


async def get_reference_workflow(
    language: str,
    framework: Optional[str] = None
) -> Optional[str]:
    """Get reference workflow from ChromaDB"""
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
        print(f"[ChromaDB] Error getting reference workflow: {e}")

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
                print(f"[ChromaDB] Collection '{SUCCESSFUL_PIPELINES_COLLECTION}' not found")
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
                    try:
                        # Document is stored as markdown with embedded code blocks
                        # Extract workflow from ```yaml ... ``` block
                        yaml_match = re.search(r'```yaml\s*\n(.*?)```', doc, re.DOTALL)
                        dockerfile_match = re.search(r'```dockerfile\s*\n(.*?)```', doc, re.DOTALL)

                        workflow = yaml_match.group(1).strip() if yaml_match else ""
                        dockerfile = dockerfile_match.group(1).strip() if dockerfile_match else ""

                        if workflow:
                            return {
                                "workflow": workflow,
                                "dockerfile": dockerfile,
                                "source": "chromadb-successful"
                            }
                    except Exception as parse_err:
                        print(f"[ChromaDB] Error parsing stored template: {parse_err}")

    except Exception as e:
        print(f"[ChromaDB] Error getting best template: {e}")

    return None
