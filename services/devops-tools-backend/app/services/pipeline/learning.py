"""
Reinforcement Learning / Feedback Functions

Standalone async functions for RL feedback loop and pipeline result recording.
"""
from typing import Dict, Any, List

import httpx

from app.config import tools_manager
from app.integrations.chromadb import ChromaDBIntegration

from .analyzer import parse_gitlab_url, analyze_repository
from .templates import store_successful_pipeline


ALLOWED_SKIPPED_JOBS = {"notify_failure"}
ALLOWED_IN_PROGRESS_JOBS = {"learn_record"}
BLOCKING_JOB_STATES = {
    "failed",
    "canceled",
    "manual",
    "scheduled",
}


def _get_chromadb() -> ChromaDBIntegration:
    chromadb_config = tools_manager.get_tool("chromadb")
    return ChromaDBIntegration(chromadb_config)


def _pipeline_warning_reasons(pipeline: Dict[str, Any]) -> List[str]:
    detailed_status = pipeline.get("detailed_status") or {}
    fields = [
        str(detailed_status.get("group", "")),
        str(detailed_status.get("label", "")),
        str(detailed_status.get("text", "")),
        str(detailed_status.get("icon", "")),
    ]
    return [field for field in fields if "warning" in field.lower()]


def _job_label(job: Dict[str, Any]) -> str:
    name = job.get("name") or "unknown"
    status = job.get("status") or "unknown"
    allow_failure = " allow_failure=true" if job.get("allow_failure") else ""
    return f"{name}:{status}{allow_failure}"


def _blocking_jobs_for_strict_success(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return jobs that prove the pipeline is not a clean all-stage success."""
    blocking = []
    for job in jobs:
        name = job.get("name") or ""
        status = job.get("status") or ""

        if name in ALLOWED_IN_PROGRESS_JOBS and status in {"created", "pending", "running", "success"}:
            continue
        if name in ALLOWED_SKIPPED_JOBS and status == "skipped":
            continue
        if status == "success":
            continue

        if status in BLOCKING_JOB_STATES or status in {"skipped", "created", "pending", "running"}:
            blocking.append(job)

    return blocking


async def get_relevant_feedback(language: str, framework: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Feedback documents are intentionally disabled for GitLab pipeline
    generation. ChromaDB must contain only:
    - gitlab_successful_template: verified successful RL templates
    - Generic_template: generic stage reference used by LLM fallback
    """
    return []


async def store_feedback(
    original_gitlab_ci: str,
    corrected_gitlab_ci: str,
    original_dockerfile: str,
    corrected_dockerfile: str,
    language: str,
    framework: str,
    error_type: str,
    fix_description: str
) -> bool:
    """
    Disabled to keep ChromaDB restricted to the two GitLab template sections.
    """
    print("[RL] Feedback storage skipped; only successful templates are stored.")
    return False


async def record_pipeline_result(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    pipeline_id: int
) -> Dict[str, Any]:
    """
    Check pipeline status and record the result for reinforcement learning.
    If successful, stores the configuration. If failed, records failure info.

    This is the main entry point for the RL feedback loop.

    Args:
        repo_url: GitLab repository URL
        gitlab_token: GitLab access token
        branch: Branch name
        pipeline_id: Pipeline ID to check

    Returns:
        Dict with status and learning result
    """
    try:
        parsed = parse_gitlab_url(repo_url)

        async with httpx.AsyncClient() as client:
            headers = {"PRIVATE-TOKEN": gitlab_token}

            # Get pipeline details
            pipeline_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines/{pipeline_id}"
            pipeline_resp = await client.get(pipeline_url, headers=headers)

            if pipeline_resp.status_code != 200:
                return {"success": False, "error": "Could not fetch pipeline details"}

            pipeline = pipeline_resp.json()
            status = pipeline.get('status')

            # Get pipeline jobs to see which stages passed
            jobs_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/pipelines/{pipeline_id}/jobs"
            jobs_resp = await client.get(jobs_url, headers=headers, params={"per_page": 100})
            jobs = jobs_resp.json() if jobs_resp.status_code == 200 else []

            stages_passed = [job['name'] for job in jobs if job.get('status') == 'success']
            stages_failed = [job['name'] for job in jobs if job.get('status') == 'failed']
            stages_running = [job['name'] for job in jobs if job.get('status') == 'running']
            stages_skipped = [job['name'] for job in jobs if job.get('status') == 'skipped']
            warning_reasons = _pipeline_warning_reasons(pipeline)
            blocking_jobs = _blocking_jobs_for_strict_success(jobs)

            # Handle the case when called from the learn_record job itself
            # If pipeline is "running" but only learn_record is running and all other jobs passed,
            # we can consider it as a successful pipeline
            effective_status = status
            if status == 'running':
                # Check if only learn-related jobs are still running
                non_learn_running = [j for j in stages_running if 'learn' not in j.lower()]
                if not non_learn_running and not blocking_jobs and not warning_reasons:
                    # All non-learn jobs have passed, treat as success
                    effective_status = 'success'
                    print(f"[RL] Pipeline {pipeline_id} is running but all non-learn stages passed - treating as success")
                else:
                    return {
                        "success": True,
                        "status": status,
                        "message": (
                            f"Pipeline still {status} or has non-passing jobs; "
                            "will not record until every required job is green"
                        ),
                        "non_passing_jobs": [_job_label(job) for job in blocking_jobs],
                        "warning_reasons": warning_reasons,
                        "recorded": False
                    }
            elif status not in ['success', 'failed']:
                return {
                    "success": True,
                    "status": status,
                    "message": f"Pipeline still {status}, will record when complete",
                    "recorded": False
                }

            status = effective_status

            # Analyze repository for language/framework
            analysis = await analyze_repository(repo_url, gitlab_token)
            language = analysis.get('language', 'unknown')
            framework = analysis.get('framework', 'generic')

            # Get the .gitlab-ci.yml and Dockerfile content
            gitlab_ci_content = ""
            dockerfile_content = ""

            for filename in ['.gitlab-ci.yml', 'Dockerfile']:
                file_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/files/{filename}/raw"
                file_resp = await client.get(file_url, headers=headers, params={"ref": branch})
                if file_resp.status_code == 200:
                    if filename == '.gitlab-ci.yml':
                        gitlab_ci_content = file_resp.text
                    else:
                        dockerfile_content = file_resp.text

            result = {
                "success": True,
                "pipeline_id": pipeline_id,
                "status": status,
                "language": language,
                "framework": framework,
                "stages_passed": stages_passed,
                "stages_failed": stages_failed,
                "stages_skipped": stages_skipped,
                "warning_reasons": warning_reasons,
                "non_passing_jobs": [_job_label(job) for job in blocking_jobs],
                "duration": pipeline.get('duration'),
                "recorded": False
            }

            if status == 'success':
                direct_rag_markers = (
                    "Pipeline Source: RAG (proven template from ChromaDB)",
                    'PIPELINE_SOURCE: "RAG (proven template from ChromaDB)"',
                    'PIPELINE_GENERATOR: "chromadb-direct"',
                )
                if any(marker in gitlab_ci_content for marker in direct_rag_markers):
                    print(
                        f"[RL] Pipeline {pipeline_id} is a direct RAG reuse "
                        f"({language}/{framework}) — NOT saving back to RAG"
                    )
                    result["message"] = (
                        "Pipeline succeeded from direct RAG reuse. NOT saving "
                        "back to RAG; direct RAG hits already came from "
                        "gitlab_successful_template and operator deletes must "
                        "remain effective."
                    )
                    result["recorded"] = False
                    return result

                # STRICT QUALITY GATE: Store to RAG only when GitLab reports a
                # clean success and every real job is green. GitLab marks a
                # pipeline as `success` even when an allow_failure job failed;
                # that appears as detailed_status=success-with-warnings and
                # must never become a reusable RAG template.
                if warning_reasons or blocking_jobs:
                    print(
                        f"[RL] Pipeline {pipeline_id} is not a clean success "
                        f"(warnings={warning_reasons}, jobs={[_job_label(job) for job in blocking_jobs]}) "
                        "— NOT saving to RAG"
                    )
                    result["message"] = (
                        "Pipeline did not pass cleanly. GitLab reported warnings "
                        f"{warning_reasons or 'none'} and non-passing jobs "
                        f"{[_job_label(job) for job in blocking_jobs] or 'none'}. "
                        "NOT saving to RAG DB; only all-green pipelines are stored."
                    )
                    result["recorded"] = False
                else:
                    # All stages passed — store as proven template
                    stored = await store_successful_pipeline(
                        repo_url=repo_url,
                        gitlab_token=gitlab_token,
                        branch=branch,
                        pipeline_id=pipeline_id,
                        gitlab_ci_content=gitlab_ci_content,
                        dockerfile_content=dockerfile_content,
                        language=language,
                        framework=framework,
                        duration=pipeline.get('duration'),
                        stages_passed=stages_passed
                    )
                    result["recorded"] = stored
                    result["message"] = (
                        "Pipeline succeeded with ALL stages passing. "
                        "Configuration stored for reinforcement learning."
                        if stored else
                        "Pipeline succeeded with ALL stages passing, but RAG storage "
                        "was skipped because the exact template already exists or storage failed."
                    )
            else:
                # Record failure for analysis
                result["message"] = f"Pipeline failed. Failed stages: {', '.join(stages_failed)}"
                # Optionally store failure patterns for learning what NOT to do
                # This could be implemented later for negative reinforcement

            return result

    except Exception as e:
        print(f"[RL] Error recording pipeline result: {e}")
        return {"success": False, "error": str(e)}


async def compare_and_learn(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    generated_files: Dict[str, str]
) -> Dict[str, Any]:
    """
    Compare current files in repo with generated files and learn from differences.
    Called after manual fixes to learn from corrections.
    """
    parsed = parse_gitlab_url(repo_url)

    async with httpx.AsyncClient() as client:
        headers = {"PRIVATE-TOKEN": gitlab_token}

        differences = {}

        for filename, original_content in generated_files.items():
            # Get current file content from repo
            file_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/files/{filename.replace('/', '%2F')}/raw"
            resp = await client.get(
                file_url,
                headers=headers,
                params={"ref": branch}
            )

            if resp.status_code == 200:
                current_content = resp.text

                if current_content.strip() != original_content.strip():
                    differences[filename] = {
                        "original": original_content,
                        "corrected": current_content,
                        "changed": True
                    }
                else:
                    differences[filename] = {"changed": False}

        return differences
