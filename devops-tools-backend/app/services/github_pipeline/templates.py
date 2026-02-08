"""
ChromaDB template operations for GitHub Actions workflows.

Handles retrieving reference workflows and best-performing templates.
"""
import yaml
import httpx
from typing import Dict, Any, Optional

from app.config import settings


FEEDBACK_COLLECTION = "github_actions_feedback"
TEMPLATES_COLLECTION = "github_actions_templates"
SUCCESSFUL_PIPELINES_COLLECTION = "github_actions_successful_pipelines"


def _ensure_learn_job(workflow: str) -> str:
    """Ensure the learn-record job exists in the workflow"""
    try:
        parsed = yaml.safe_load(workflow)
        if not parsed or 'jobs' not in parsed:
            return workflow

        jobs = parsed.get('jobs', {})

        # Check if learn-record job exists
        if 'learn-record' not in jobs:
            # Add learn-record job
            jobs['learn-record'] = {
                'runs-on': 'self-hosted',
                'needs': 'push-release',
                'if': 'success()',
                'steps': [
                    {'uses': 'actions/checkout@v4'},
                    {
                        'name': 'Record Pipeline Success for RL',
                        'run': '''curl -s -X POST "${{ env.DEVOPS_BACKEND_URL }}/api/v1/github-pipeline/learn/record" \\
  -H "Content-Type: application/json" \\
  -d '{
    "repo_url": "${{ github.server_url }}/${{ github.repository }}",
    "github_token": "${{ secrets.GITHUB_TOKEN }}",
    "branch": "${{ github.ref_name }}",
    "run_id": ${{ github.run_id }}
  }' && echo "SUCCESS: Configuration recorded for RL"'''
                    }
                ]
            }
            parsed['jobs'] = jobs
            return yaml.dump(parsed, default_flow_style=False, sort_keys=False)

        return workflow
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
            # First try exact match with language + framework
            if framework:
                response = await client.post(
                    f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{TEMPLATES_COLLECTION}/get",
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
                f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{TEMPLATES_COLLECTION}/get",
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
            where_filter = {"language": language}
            if framework:
                where_filter = {
                    "$and": [
                        {"language": language},
                        {"framework": framework}
                    ]
                }

            response = await client.post(
                f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{SUCCESSFUL_PIPELINES_COLLECTION}/get",
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
                        parsed = yaml.safe_load(doc)
                        return {
                            "workflow": parsed.get("workflow", ""),
                            "dockerfile": parsed.get("dockerfile", ""),
                            "source": "chromadb-successful"
                        }
                    except:
                        pass

    except Exception as e:
        print(f"[ChromaDB] Error getting best template: {e}")

    return None
