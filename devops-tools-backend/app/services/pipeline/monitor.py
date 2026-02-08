"""
Pipeline Monitoring Functions

Standalone async function for monitoring GitLab pipeline status.
"""
from typing import Dict, Any

import httpx

from .analyzer import parse_gitlab_url


async def get_pipeline_status(
    repo_url: str,
    gitlab_token: str,
    branch: str
) -> Dict[str, Any]:
    """Get the latest pipeline status for a branch"""
    parsed = parse_gitlab_url(repo_url)

    async with httpx.AsyncClient() as client:
        headers = {"PRIVATE-TOKEN": gitlab_token}

        # Get pipelines for the branch
        pipelines_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines"
        resp = await client.get(
            pipelines_url,
            headers=headers,
            params={"ref": branch, "per_page": 1}
        )
        resp.raise_for_status()
        pipelines = resp.json()

        if not pipelines:
            return {"status": "no_pipeline", "message": "No pipeline found for this branch"}

        pipeline = pipelines[0]

        # Get detailed pipeline info
        pipeline_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines/{pipeline['id']}"
        detail_resp = await client.get(pipeline_url, headers=headers)
        detail = detail_resp.json()

        # Get jobs if pipeline failed
        jobs = []
        if pipeline['status'] in ['failed', 'canceled']:
            jobs_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines/{pipeline['id']}/jobs"
            jobs_resp = await client.get(jobs_url, headers=headers)
            jobs = jobs_resp.json()

        return {
            "pipeline_id": pipeline['id'],
            "status": pipeline['status'],
            "web_url": pipeline.get('web_url'),
            "created_at": pipeline.get('created_at'),
            "finished_at": detail.get('finished_at'),
            "duration": detail.get('duration'),
            "failed_jobs": [
                {"name": j['name'], "stage": j['stage'], "status": j['status']}
                for j in jobs if j['status'] == 'failed'
            ]
        }
