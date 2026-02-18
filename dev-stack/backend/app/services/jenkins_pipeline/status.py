"""
File: status.py
Purpose: Interfaces with the Jenkins REST API for build operations: querying build status
    and stage details via the workflow API, triggering builds and multibranch branch scans
    (with CSRF crumb handling), and recording basic build results to ChromaDB for RL.
When Used: Called by the generator facade and the chat endpoint to monitor build progress
    after committing pipeline files. trigger_scan() is invoked after each commit to make
    Jenkins discover the new branch. get_build_status() and get_build_stages() are polled
    during build monitoring. record_build_result() is the lightweight RL recording path
    (job name + build number only, without fetching repo files).
Why Created: Separated from the generator to isolate Jenkins API interactions (authentication,
    crumb tokens, REST endpoints) from pipeline generation logic, and to distinguish the
    simple status-module recording from the full learning-module recording that fetches
    actual file contents from Gitea.
"""
import httpx
from typing import Dict, Any, Optional, List

from app.config import settings


async def _get_crumb(client: httpx.AsyncClient, auth: tuple) -> Optional[Dict[str, str]]:
    """Get Jenkins crumb token for CSRF protection."""
    try:
        response = await client.get(
            f"{settings.jenkins_url}/crumbIssuer/api/json",
            auth=auth
        )
        if response.status_code == 200:
            data = response.json()
            return {data["crumbRequestField"]: data["crumb"]}
    except Exception:
        pass
    return None


async def get_build_status(
    job_name: str,
    build_number: Optional[int] = None
) -> Dict[str, Any]:
    """Get Jenkins build status via REST API."""
    auth = (settings.jenkins_username, settings.jenkins_password)

    if build_number:
        url = f"{settings.jenkins_url}/job/{job_name}/{build_number}/api/json"
    else:
        url = f"{settings.jenkins_url}/job/{job_name}/lastBuild/api/json"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, auth=auth)
            if response.status_code == 200:
                data = response.json()
                return {
                    "build_number": data["number"],
                    "status": "building" if data.get("building") else (data.get("result", "UNKNOWN")).lower(),
                    "duration": data.get("duration", 0),
                    "timestamp": data.get("timestamp", 0),
                    "url": data.get("url", ""),
                    "display_name": data.get("displayName", ""),
                    "building": data.get("building", False),
                }
            elif response.status_code == 404:
                return {"status": "not_found", "error": f"Job or build not found: {job_name}"}
    except Exception as e:
        print(f"[Jenkins] Error getting build status: {e}")

    return {"status": "error", "error": "Failed to get build status"}


async def get_build_stages(
    job_name: str,
    build_number: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get stage details from Jenkins workflow API."""
    auth = (settings.jenkins_username, settings.jenkins_password)

    if build_number:
        url = f"{settings.jenkins_url}/job/{job_name}/{build_number}/wfapi/describe"
    else:
        url = f"{settings.jenkins_url}/job/{job_name}/lastBuild/wfapi/describe"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, auth=auth)
            if response.status_code == 200:
                data = response.json()
                stages = []
                for s in data.get("stages", []):
                    stage_status = s.get("status", "UNKNOWN")
                    duration_ms = s.get("durationMillis", 0)
                    stages.append({
                        "name": s.get("name", ""),
                        "status": stage_status,
                        "duration_sec": round(duration_ms / 1000, 1),
                    })
                return stages
    except Exception as e:
        print(f"[Jenkins] Error getting build stages: {e}")

    return []


async def trigger_scan(project_name: str) -> Dict[str, Any]:
    """Trigger a multibranch pipeline branch scan."""
    auth = (settings.jenkins_username, settings.jenkins_password)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            crumb = await _get_crumb(client, auth)
            if crumb:
                headers.update(crumb)

            response = await client.post(
                f"{settings.jenkins_url}/job/{project_name}/build?delay=0sec",
                auth=auth,
                headers=headers,
            )

            if response.status_code in [200, 201, 302]:
                return {"success": True, "message": f"Branch scan triggered for {project_name}"}

            return {"success": False, "error": f"Scan trigger failed: HTTP {response.status_code}"}
    except Exception as e:
        print(f"[Jenkins] Error triggering scan: {e}")
        return {"success": False, "error": str(e)}


async def trigger_build(job_name: str) -> Dict[str, Any]:
    """Trigger a Jenkins build via REST API."""
    auth = (settings.jenkins_username, settings.jenkins_password)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get crumb for CSRF protection
            headers = {}
            crumb = await _get_crumb(client, auth)
            if crumb:
                headers.update(crumb)

            response = await client.post(
                f"{settings.jenkins_url}/job/{job_name}/build",
                auth=auth,
                headers=headers,
            )

            if response.status_code in [200, 201, 302]:
                # Jenkins returns 201 or 302 on success
                return {
                    "success": True,
                    "message": f"Build triggered for {job_name}",
                    "queue_url": response.headers.get("Location", "")
                }

            return {
                "success": False,
                "error": f"Failed to trigger build: HTTP {response.status_code}"
            }
    except Exception as e:
        print(f"[Jenkins] Error triggering build: {e}")
        return {"success": False, "error": str(e)}


async def record_build_result(
    job_name: str,
    build_number: int,
    status: str = "success"
) -> Dict[str, Any]:
    """Record build result for reinforcement learning."""
    build_status = await get_build_status(job_name, build_number)

    if build_status.get("status") == "success" or status == "success":
        # Store in ChromaDB for RL
        try:
            chromadb_url = settings.chromadb_url
            async with httpx.AsyncClient(timeout=30.0) as client:
                import hashlib
                doc_id = f"jenkins_success_{job_name}_{build_number}"
                content_hash = hashlib.md5(f"{job_name}:{build_number}".encode()).hexdigest()[:12]

                await client.post(
                    f"{chromadb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/jenkins_successful_pipelines/add",
                    json={
                        "ids": [doc_id],
                        "documents": [f"Jenkins build {job_name} #{build_number} succeeded"],
                        "metadatas": [{
                            "job_name": job_name,
                            "build_number": build_number,
                            "status": "success",
                            "content_hash": content_hash,
                            "source": "jenkins-auto",
                        }]
                    }
                )

                return {"success": True, "recorded": True, "doc_id": doc_id}
        except Exception as e:
            print(f"[ChromaDB] Error recording build result: {e}")
            return {"success": True, "recorded": False, "error": str(e)}

    return {"success": False, "error": "Build not successful"}
