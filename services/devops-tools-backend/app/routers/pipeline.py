"""
Pipeline Generator API Router (GitLab side).

Provides endpoints for:
1. Generating GitLab CI/CD pipelines and Dockerfiles
2. Committing to GitLab repositories
3. Monitoring pipeline status
4. Storing and retrieving feedback for reinforcement learning
5. Self-healing pipeline monitor (mirror of GitHub Actions self-heal flow):
   commits the generated files, polls for the next pipeline, and on failure
   pulls the failing job's trace, calls the LLM fixer, re-seeds images, and
   re-commits — up to N attempts. The same `progress_store` singleton used by
   the GitHub side surfaces real-time status to the frontend.
"""
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.integrations.llm_provider import get_active_provider_name
from app.services.gitlab_dry_run_validator import gitlab_dry_run_validator
from app.services.gitlab_llm_fixer import gitlab_llm_fixer
from app.services.pipeline.image_seeder import ensure_images_in_nexus
from app.services.pipeline_generator import pipeline_generator
from app.services.pipeline_progress import progress_store

router = APIRouter(prefix="/pipeline", tags=["Pipeline Generator"])


# ============================================================================
# Constants
# ============================================================================

# GitLab pipeline statuses we treat as "still pending" — we keep polling.
_PIPELINE_PENDING_STATUSES = {
    "created", "waiting_for_resource", "preparing", "pending",
    "scheduled", "manual",
}
# Statuses that indicate the pipeline is actively running.
_PIPELINE_RUNNING_STATUSES = {"running"}
# Terminal statuses we record once and stop polling.
_PIPELINE_TERMINAL_STATUSES = {"success", "failed", "canceled", "skipped"}

# Per-job emoji map for the status breakdown in the progress message.
_JOB_STATUS_ICONS = {
    "success": "✅",       # green check
    "failed": "❌",        # red X
    "running": "⏳",       # hourglass
    "pending": "⏸",       # double bar
    "created": "⬜",       # white square
    "manual": "✋",        # raised hand
    "skipped": "⏭",       # next track
    "canceled": "⛔",      # no entry
    "waiting_for_resource": "⏸",
    "preparing": "⏳",
    "scheduled": "⏸",
}

_ALLOWED_CLEAN_SKIPPED_JOBS = {"notify_failure"}
_ALLOWED_CLEAN_IN_PROGRESS_JOBS = {"learn_record"}
_BLOCKING_CLEAN_JOB_STATES = {
    "failed",
    "canceled",
    "manual",
    "scheduled",
}


# ============================================================================
# Helpers — GitLab API plumbing for the monitor
# ============================================================================

def _gitlab_api_base() -> str:
    """Container-internal GitLab API base, e.g. ``http://gitlab-server``."""
    return settings.gitlab_url.rstrip('/')


def _gitlab_public_base() -> str:
    """User-facing GitLab base URL the portal links to from the browser.

    Prefer the Cloudflare public host so links stay on deepaksharma.live.
    Tailscale is kept only as a legacy fallback for tailnet-only operation.
    """
    public_domain = getattr(settings, "public_base_domain", None)
    if public_domain:
        return f"https://gitlab.{public_domain.strip('/')}/gitlab"

    base = (
        getattr(settings, "public_base_url", None)
        or getattr(settings, "tailscale_base_url", None)
    )
    if base:
        return f"{base.rstrip('/')}/gitlab"
    # Fallback — in-cluster URL (only useful from the host network).
    return settings.gitlab_url.rstrip('/')


def _gitlab_headers(gitlab_token: str) -> Dict[str, str]:
    return {"PRIVATE-TOKEN": gitlab_token}


async def _fetch_failed_job_log(
    gl_base: str,
    headers: Dict[str, str],
    project_id: int,
    pipeline_id: int,
) -> tuple:
    """Fetch the trace of the first failed job in a GitLab pipeline.

    Returns ``(log_text or None, job_name or None)`` so the caller can decide
    whether to invoke the LLM fixer or fall back to a static-validation path.
    The log is truncated to 8000 characters to keep the LLM prompt bounded.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            jobs_resp = await client.get(
                f"{gl_base}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs",
                headers=headers,
                params={"per_page": 100},
            )
            if jobs_resp.status_code != 200:
                return None, None

            jobs_list = jobs_resp.json() or []
            failed_job = next(
                (j for j in jobs_list if j.get("status") == "failed"),
                None,
            )
            if not failed_job:
                return None, None

            job_name = failed_job.get("name", "unknown")
            job_id = failed_job.get("id")
            if not job_id:
                return None, job_name

            trace_resp = await client.get(
                f"{gl_base}/api/v4/projects/{project_id}/jobs/{job_id}/trace",
                headers=headers,
            )
            if trace_resp.status_code == 200:
                log_text = trace_resp.text or ""
                if log_text and len(log_text) > 10:
                    if len(log_text) > 8000:
                        log_text = log_text[-8000:]
                    return log_text, job_name
    except Exception as e:
        print(f"[GitLab Monitor] Failed to fetch job logs: {e}")

    return None, None


def _job_breakdown(jobs_list: List[Dict[str, Any]]) -> str:
    """Build the per-job emoji breakdown displayed in the progress message."""
    if not jobs_list:
        return ""
    parts = []
    for j in jobs_list:
        status = (j.get("status") or "pending").lower()
        icon = _JOB_STATUS_ICONS.get(status, "⬜")
        parts.append(f"{icon} {j.get('name', 'unknown')}")
    return " | " + " → ".join(parts)


def _pipeline_warning_reasons(pipeline: Dict[str, Any]) -> List[str]:
    """Return GitLab detailed_status fields that prove a warning state."""
    detailed_status = pipeline.get("detailed_status") or {}
    fields = [
        str(detailed_status.get("group", "")),
        str(detailed_status.get("label", "")),
        str(detailed_status.get("text", "")),
        str(detailed_status.get("icon", "")),
        str(detailed_status.get("tooltip", "")),
    ]
    return [field for field in fields if "warning" in field.lower()]


def _job_label(job: Dict[str, Any]) -> str:
    name = job.get("name") or "unknown"
    status = job.get("status") or "unknown"
    allow_failure = " allow_failure=true" if job.get("allow_failure") else ""
    return f"{name}:{status}{allow_failure}"


def _blocking_jobs_for_clean_success(jobs_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Jobs that make a top-level GitLab success unusable for RAG/RL.

    GitLab reports `success` when an allow_failure job fails. For this flow,
    that is not a successful template and must enter self-heal.
    """
    blocking = []
    for job in jobs_list:
        name = job.get("name") or ""
        status = (job.get("status") or "").lower()

        if name in _ALLOWED_CLEAN_IN_PROGRESS_JOBS and status in {
            "created", "pending", "running", "success"
        }:
            continue
        if name in _ALLOWED_CLEAN_SKIPPED_JOBS and status == "skipped":
            continue
        if status == "success":
            continue
        if status in _BLOCKING_CLEAN_JOB_STATES or status in {
            "skipped", "created", "pending", "running"
        }:
            blocking.append(job)

    return blocking


async def _get_pipeline_detail_and_jobs(
    gl_base: str,
    headers: Dict[str, str],
    project_id: int,
    pipeline_id: int,
) -> tuple:
    """Fetch detailed pipeline status plus jobs for clean-success decisions."""
    pipeline_detail: Dict[str, Any] = {}
    jobs_list: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        detail_resp = await client.get(
            f"{gl_base}/api/v4/projects/{project_id}/pipelines/{pipeline_id}",
            headers=headers,
        )
        if detail_resp.status_code == 200:
            pipeline_detail = detail_resp.json() or {}

        jobs_resp = await client.get(
            f"{gl_base}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs",
            headers=headers,
            params={"per_page": 100},
        )
        if jobs_resp.status_code == 200:
            jobs_list = jobs_resp.json() or []

    return pipeline_detail, jobs_list


async def _latest_pipeline_id_for_ref(
    gl_base: str,
    headers: Dict[str, str],
    project_ref: Any,
    branch: str,
) -> int:
    """Return the latest pipeline id for a ref, or 0 when none exists.

    The monitor uses this as a cursor before a new commit is pushed. Without
    it, rerunning on an existing branch can pick up an old failed pipeline and
    self-heal the wrong run before GitLab registers the fresh commit pipeline.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{gl_base}/api/v4/projects/{project_ref}/pipelines",
                headers=headers,
                params={"ref": branch, "per_page": 1},
            )
        if resp.status_code != 200:
            return 0
        pipelines = resp.json() or []
        if not pipelines:
            return 0
        return int(pipelines[0].get("id") or 0)
    except Exception as exc:
        print(f"[GitLab Monitor] Could not read existing pipeline cursor: {exc}")
        return 0


# ============================================================================
# Background tasks
# ============================================================================

async def monitor_pipeline_for_learning(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    project_id: int,
    max_wait_minutes: int = 15,
    check_interval_seconds: int = 30,
    previous_max_pipeline_id: int = 0,
):
    """RAG/status-only monitor.

    This path is used for ``chromadb-direct`` RAG hits. It does NOT call the
    LLM fixer, does NOT mutate the branch on failure, and does NOT write back
    to RAG. A saved RAG template should pass first attempt; if it fails,
    surface that as a template/runtime issue instead of silently entering
    self-heal. RAG writes are reserved for LLM/self-heal generated pipelines.
    """
    gl_base = _gitlab_api_base()
    headers = _gitlab_headers(gitlab_token)
    parsed = pipeline_generator.parse_gitlab_url(repo_url)
    project_path = parsed.get('path', '')
    public_base = _gitlab_public_base()
    pipelines_browser_url = f"{public_base}/{project_path}/-/pipelines?ref={branch}"

    if project_id:
        progress_store.set_urls(
            project_id, branch, pipelines_browser_url=pipelines_browser_url,
        )

    print(
        f"[RAG Monitor] Starting status-only monitor for "
        f"{project_path} branch={branch}"
    )

    max_checks = (max_wait_minutes * 60) // check_interval_seconds

    for check_num in range(max_checks):
        try:
            if check_num > 0:
                await asyncio.sleep(check_interval_seconds)

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{gl_base}/api/v4/projects/{project_id}/pipelines",
                    headers=headers,
                    params={"ref": branch, "per_page": 10},
                )

            if resp.status_code != 200:
                print(f"[RAG Monitor] Failed to get pipelines: {resp.status_code}")
                if project_id:
                    progress_store.update(
                        project_id, branch, "build_running",
                        "RAG template committed. Waiting for GitLab API...",
                    )
                continue

            pipelines = resp.json() or []
            pipeline = None
            for candidate in pipelines:
                cid = int(candidate.get('id') or 0)
                cstatus = (candidate.get('status') or '').lower()
                if cid <= previous_max_pipeline_id or cstatus == 'canceled':
                    continue
                pipeline = candidate
                break

            if not pipeline:
                if project_id:
                    progress_store.update(
                        project_id, branch, "build_running",
                        f"RAG template committed. Waiting for new pipeline "
                        f"(after #{previous_max_pipeline_id})...",
                    )
                continue

            pipeline_id = int(pipeline.get('id') or 0)
            status = (pipeline.get('status') or 'unknown').lower()
            if project_id:
                progress_store.set_pipeline_id(project_id, branch, pipeline_id)
                progress_store.set_urls(
                    project_id,
                    branch,
                    pipeline_web_url=f"{public_base}/{project_path}/-/pipelines/{pipeline_id}",
                )

            jobs_info = ""
            warning_reasons: List[str] = []
            blocking_jobs: List[Dict[str, Any]] = []
            try:
                pipeline_detail, jobs_list = await _get_pipeline_detail_and_jobs(
                    gl_base, headers, project_id, pipeline_id,
                )
                if pipeline_detail:
                    status = (pipeline_detail.get("status") or status).lower()
                    warning_reasons = _pipeline_warning_reasons(pipeline_detail)
                blocking_jobs = _blocking_jobs_for_clean_success(jobs_list)
                jobs_info = _job_breakdown(jobs_list)
            except Exception:
                pass

            dirty_success = status == "success" and (
                bool(warning_reasons) or bool(blocking_jobs)
            )

            if status in _PIPELINE_PENDING_STATUSES:
                if project_id:
                    progress_store.update(
                        project_id, branch, "build_running",
                        f"RAG template pipeline #{pipeline_id} queued ({status})... | "
                        f"[Pipelines]({pipelines_browser_url})",
                    )
                continue

            if status in _PIPELINE_RUNNING_STATUSES:
                if project_id:
                    progress_store.update(
                        project_id, branch, "build_running",
                        f"RAG template pipeline #{pipeline_id} running{jobs_info} | "
                        f"[Pipelines]({pipelines_browser_url})",
                    )
                continue

            if dirty_success:
                issue_text = (
                    f"warnings={warning_reasons or 'none'}, "
                    f"non_green_jobs={[_job_label(job) for job in blocking_jobs] or 'none'}"
                )
                print(
                    f"[RAG Monitor] Pipeline {pipeline_id} passed with warnings "
                    f"({issue_text}); treating as failed template run."
                )
                if project_id:
                    progress_store.complete(
                        project_id, branch, "failed",
                        f"RAG template pipeline ended with warnings. {issue_text}."
                        f"{jobs_info}\nNo LLM/self-heal path was used for "
                        f"this chromadb-direct RAG run. "
                        f"[View Pipelines]({pipelines_browser_url})",
                    )
                return

            if status in _PIPELINE_TERMINAL_STATUSES:
                if status == "success":
                    print(
                        f"[RAG Monitor] Pipeline {pipeline_id} succeeded. "
                        f"No RAG write executed for chromadb-direct reuse."
                    )
                    if project_id:
                        progress_store.complete(
                            project_id, branch, "success",
                            f"RAG template pipeline succeeded first attempt!{jobs_info}\n"
                            f"No RAG write executed for direct RAG reuse. "
                            f"[View Pipelines]({pipelines_browser_url})",
                        )
                else:
                    print(
                        f"[RAG Monitor] RAG template pipeline {pipeline_id} "
                        f"ended with status '{status}'. No LLM/self-heal executed."
                    )
                    if project_id:
                        progress_store.complete(
                            project_id, branch, "failed",
                            f"RAG template pipeline ended with status: {status}."
                            f"{jobs_info}\nNo LLM/self-heal path was used for "
                            f"this chromadb-direct RAG run. "
                            f"[View Pipelines]({pipelines_browser_url})",
                        )
                return
        except Exception as e:
            print(f"[RAG Monitor] Error checking pipeline: {e}")

    print(
        f"[RAG Monitor] Timeout waiting for pipeline on {branch} "
        f"after {max_wait_minutes} minutes"
    )
    if project_id:
        progress_store.complete(
            project_id, branch, "failed",
            f"Timeout waiting for RAG template pipeline after "
            f"{max_wait_minutes} minutes.",
        )


async def monitor_pipeline_with_self_heal(
    repo_url: str,
    gitlab_token: str,
    branch: str,
    project_id: int,
    gitlab_ci: str,
    dockerfile: str,
    language: str = "unknown",
    framework: str = "generic",
    max_wait_minutes: int = 15,
    check_interval_seconds: int = 30,
    max_heal_attempts: int = 10,
    previous_max_pipeline_id: int = 0,
):
    """Self-healing monitor — mirrors the GitHub Actions implementation.

    Loop:
      1. Wait for a new GitLab pipeline (id > previous_max_pipeline_id) to
         finish on ``branch``.
      2. On terminal status:
         - ``success``  -> ``record_pipeline_result`` (stores to RAG) -> done.
         - ``failed`` / ``canceled`` -> fetch the first failed job's trace,
           call ``gitlab_llm_fixer.generate_fix(...)``, re-seed any new images
           via ``ensure_images_in_nexus``, and ``commit_to_gitlab`` the updated
           ``.gitlab-ci.yml`` + ``Dockerfile`` onto the same branch. GitLab
           auto-triggers a fresh pipeline; bookkeeping continues with the new
           pipeline id.
         - other terminal (``skipped``) -> stop, mark progress failed.
      3. Idempotency: if the LLM fixer returns identical files, skip the
         commit, keep progress running, and retry with the no-diff feedback.
      4. Hard cap: ``max_heal_attempts`` self-heals. After that we mark the
         progress failed and stop.

    The ``progress_store`` singleton is updated continuously so the frontend
    can poll ``GET /pipeline/progress/{project_id}/{branch}`` and render
    progress text + per-job emoji breakdown in real time.
    """
    gl_base = _gitlab_api_base()
    headers = _gitlab_headers(gitlab_token)

    parsed = pipeline_generator.parse_gitlab_url(repo_url)
    project_path = parsed.get('path', '')
    # Public-facing URL the user clicks to watch the run live.
    public_base = _gitlab_public_base()
    pipelines_browser_url = f"{public_base}/{project_path}/-/pipelines?ref={branch}"
    if project_id:
        progress_store.set_urls(
            project_id, branch, pipelines_browser_url=pipelines_browser_url,
        )

    print(
        f"[GitLab Monitor] Starting self-heal monitor for "
        f"{project_path} branch={branch} (max_heal={max_heal_attempts})"
    )

    current_gitlab_ci = gitlab_ci
    current_dockerfile = dockerfile
    self_heal_retry_notes: List[str] = []
    max_checks = (max_wait_minutes * 60) // check_interval_seconds
    for heal_attempt in range(max_heal_attempts + 1):
        if heal_attempt > 0:
            print(
                f"[GitLab Monitor] Monitoring self-heal attempt "
                f"{heal_attempt}/{max_heal_attempts} "
                f"(waiting for pipeline > #{previous_max_pipeline_id})"
            )
            if project_id:
                progress_store.update(
                    project_id, branch, "build_running",
                    f"Self-heal attempt {heal_attempt}/{max_heal_attempts} - "
                    f"watching for new pipeline...",
                    attempt=heal_attempt,
                )

        last_pipeline_id: Optional[int] = None
        last_status: Optional[str] = None
        last_jobs_info = ""
        run_completed = False

        for check_num in range(max_checks):
            if check_num > 0:
                await asyncio.sleep(check_interval_seconds)

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    pipelines_resp = await client.get(
                        f"{gl_base}/api/v4/projects/{project_id}/pipelines",
                        headers=headers,
                        params={"ref": branch, "per_page": 10},
                    )

                if pipelines_resp.status_code != 200:
                    if project_id:
                        progress_store.update(
                            project_id, branch, "build_running",
                            "Waiting for GitLab API...",
                        )
                    continue

                pipelines_list = pipelines_resp.json() or []
                if not pipelines_list:
                    if project_id:
                        progress_store.update(
                            project_id, branch, "build_running",
                            "Waiting for pipeline to appear...",
                        )
                    continue

                # Find the latest pipeline that is newer than our cursor and
                # not a stale-cancelled artefact (GitLab cancels older queued
                # pipelines when a new commit lands on the same ref).
                pipeline = None
                for candidate in pipelines_list:
                    cid = candidate.get('id', 0)
                    cstatus = (candidate.get('status') or '').lower()
                    if cid <= previous_max_pipeline_id:
                        continue
                    if cstatus == 'canceled':
                        # Skip cancelled-by-newer-commit artefacts
                        continue
                    pipeline = candidate
                    break

                if not pipeline:
                    if project_id:
                        progress_store.update(
                            project_id, branch, "build_running",
                            f"Waiting for new pipeline (after #{previous_max_pipeline_id})...",
                        )
                    continue

                pipeline_id_now = pipeline.get('id', 0)
                status = (pipeline.get('status') or 'unknown').lower()
                progress_store.set_pipeline_id(project_id, branch, pipeline_id_now)
                # Set the deep link to THIS specific pipeline run so the
                # portal can render a clickable "watch in GitLab" badge.
                if project_id and pipeline_id_now:
                    progress_store.set_urls(
                        project_id, branch,
                        pipeline_web_url=f"{public_base}/{project_path}/-/pipelines/{pipeline_id_now}",
                    )

                # Pull jobs for this pipeline to render the breakdown
                jobs_info = ""
                warning_reasons: List[str] = []
                blocking_jobs: List[Dict[str, Any]] = []
                try:
                    pipeline_detail, jobs_list = await _get_pipeline_detail_and_jobs(
                        gl_base, headers, project_id, pipeline_id_now,
                    )
                    if pipeline_detail:
                        status = (pipeline_detail.get("status") or status).lower()
                        warning_reasons = _pipeline_warning_reasons(pipeline_detail)
                    blocking_jobs = _blocking_jobs_for_clean_success(jobs_list)
                    jobs_info = _job_breakdown(jobs_list)
                except Exception:
                    pass
                dirty_success = status == "success" and (
                    bool(warning_reasons) or bool(blocking_jobs)
                )

                if project_id:
                    attempt_prefix = (
                        f"[Fix {heal_attempt}/{max_heal_attempts}] "
                        if heal_attempt > 0 else ""
                    )
                    if status in _PIPELINE_PENDING_STATUSES:
                        progress_store.update(
                            project_id, branch, "build_running",
                            f"{attempt_prefix}Pipeline #{pipeline_id_now} queued ({status})... | "
                            f"[Pipelines]({pipelines_browser_url})",
                            attempt=heal_attempt,
                        )
                    elif status in _PIPELINE_RUNNING_STATUSES:
                        progress_store.update(
                            project_id, branch, "build_running",
                            f"{attempt_prefix}Pipeline #{pipeline_id_now} running{jobs_info} | "
                            f"[Pipelines]({pipelines_browser_url})",
                            attempt=heal_attempt,
                        )
                    elif dirty_success:
                        issue_text = (
                            f"warnings={warning_reasons or 'none'}, "
                            f"non-green jobs={[_job_label(job) for job in blocking_jobs] or 'none'}"
                        )
                        progress_store.update(
                            project_id, branch, "build_running",
                            f"{attempt_prefix}Pipeline #{pipeline_id_now} passed with warnings; "
                            f"treating as failed for self-heal ({issue_text}).{jobs_info}",
                            attempt=heal_attempt,
                        )
                    elif status in _PIPELINE_TERMINAL_STATUSES:
                        progress_store.update(
                            project_id, branch, "build_running",
                            f"{attempt_prefix}Pipeline #{pipeline_id_now} finished: {status}{jobs_info}",
                            attempt=heal_attempt,
                        )

                if dirty_success or status in _PIPELINE_TERMINAL_STATUSES:
                    last_pipeline_id = pipeline_id_now
                    last_status = "failed" if dirty_success else status
                    last_jobs_info = jobs_info
                    run_completed = True
                    break

            except Exception as e:
                print(f"[GitLab Monitor] Error checking status: {e}")

        # ---------------------- Handle pipeline completion -----------------

        if not run_completed:
            print(
                f"[GitLab Monitor] Timeout waiting for pipeline on "
                f"{project_path} after {max_wait_minutes} min"
            )
            if project_id:
                progress_store.complete(
                    project_id, branch, "failed",
                    f"Timeout waiting for pipeline after {max_wait_minutes} minutes.",
                )
            return

        if last_status == "success":
            record_result = await pipeline_generator.record_pipeline_result(
                repo_url=repo_url,
                gitlab_token=gitlab_token,
                branch=branch,
                pipeline_id=last_pipeline_id,
            )
            attempts_msg = (
                f" after {heal_attempt} fix(es)" if heal_attempt > 0 else ""
            )
            print(
                f"[GitLab Monitor] Pipeline SUCCESS{attempts_msg} for "
                f"{project_path} - RAG record result: {record_result.get('recorded')}"
            )
            if project_id:
                progress_store.complete(
                    project_id, branch, "success",
                    f"✅ Pipeline succeeded{attempts_msg}!{last_jobs_info}\n"
                    f"[View Pipelines]({pipelines_browser_url})",
                )
            return

        if last_status not in ("failed", "canceled"):
            print(f"[GitLab Monitor] Pipeline ended with status: {last_status}")
            if project_id:
                progress_store.complete(
                    project_id, branch, "failed",
                    f"Pipeline ended with status: {last_status}",
                )
            return

        # ---------------------- FAILURE: attempt self-heal -----------------

        if heal_attempt >= max_heal_attempts:
            print(
                f"[GitLab Monitor] All {max_heal_attempts} self-heal attempts "
                f"exhausted for {project_path}"
            )
            if project_id:
                progress_store.complete(
                    project_id, branch, "failed",
                    f"❌ Pipeline failed after {max_heal_attempts} self-heal "
                    f"attempts.{last_jobs_info}\n[View Pipelines]({pipelines_browser_url})",
                )
            return

        if not current_gitlab_ci or not current_dockerfile:
            if project_id:
                progress_store.complete(
                    project_id, branch, "failed",
                    f"Pipeline failed ({last_status}). No source files available "
                    f"for self-healing.",
                )
            return

        print(
            f"[GitLab Monitor] Pipeline FAILED (#{last_pipeline_id}) - "
            f"self-heal {heal_attempt + 1}/{max_heal_attempts}"
        )
        if project_id:
            progress_store.update(
                project_id, branch, "build_running",
                f"Pipeline failed ({last_status}){last_jobs_info}. "
                f"Fetching error logs for self-heal "
                f"{heal_attempt + 1}/{max_heal_attempts}...",
                attempt=heal_attempt + 1,
            )

        error_log, failed_job_name = await _fetch_failed_job_log(
            gl_base, headers, project_id, last_pipeline_id,
        )

        fix_applied = False
        new_gitlab_ci = current_gitlab_ci
        new_dockerfile = current_dockerfile

        if error_log:
            print(
                f"[GitLab Monitor] Got error log from job "
                f"'{failed_job_name}' ({len(error_log)} chars)"
            )
            if project_id:
                progress_store.update(
                    project_id, branch, "build_running",
                    f"Got error log from '{failed_job_name}'. "
                    f"LLM generating fix attempt {heal_attempt + 1}/{max_heal_attempts}...",
                    attempt=heal_attempt + 1,
                )

            llm_error_log = error_log
            if self_heal_retry_notes:
                retry_context = "\n".join(
                    f"- {note}" for note in self_heal_retry_notes[-5:]
                )
                llm_error_log = (
                    f"{error_log}\n\n"
                    "Previous self-heal attempt feedback. Do not repeat these mistakes; "
                    "produce concrete file changes that address the runtime failure:\n"
                    f"{retry_context}\n"
                )

            fix_result = await gitlab_llm_fixer.generate_fix(
                dockerfile=current_dockerfile,
                gitlab_ci=current_gitlab_ci,
                error_log=llm_error_log,
                job_name=failed_job_name or "unknown",
                language=language,
                framework=framework,
            )

            if fix_result.success and (fix_result.gitlab_ci or fix_result.dockerfile):
                new_gitlab_ci = fix_result.gitlab_ci or current_gitlab_ci
                new_dockerfile = fix_result.dockerfile or current_dockerfile
                fix_applied = True
                print(
                    f"[GitLab Monitor] LLM fix applied: {fix_result.explanation[:200]}"
                )
                if project_id:
                    prog = progress_store.get(project_id, branch)
                    if prog:
                        prog.fixer_model_used = get_active_provider_name()
            else:
                print(
                    f"[GitLab Monitor] Log-based LLM fix failed: "
                    f"{fix_result.explanation}"
                )
                self_heal_retry_notes.append(
                    f"Attempt {heal_attempt + 1}: log-based fix failed: "
                    f"{fix_result.explanation[:500]}"
                )

        if not fix_applied:
            # Fallback: static validation-based fix using the existing
            # iterative_fix loop. Limit attempts so we don't deadlock here.
            print("[GitLab Monitor] Falling back to static validation fix...")
            if project_id:
                progress_store.update(
                    project_id, branch, "build_running",
                    "No logs or log-based fix failed. "
                    f"Trying static validation fix for attempt {heal_attempt + 1}/{max_heal_attempts}...",
                    attempt=heal_attempt + 1,
                )

            analysis = {
                "language": language,
                "framework": framework,
                "package_manager": "unknown",
            }
            static_fix = await gitlab_llm_fixer.iterative_fix(
                gitlab_ci=current_gitlab_ci,
                dockerfile=current_dockerfile,
                validator=gitlab_dry_run_validator,
                analysis=analysis,
                gitlab_token=gitlab_token,
                project_path=project_path,
                max_attempts=2,
            )
            if static_fix.get('success'):
                new_gitlab_ci = static_fix.get('gitlab_ci') or current_gitlab_ci
                new_dockerfile = static_fix.get('dockerfile') or current_dockerfile
                print("[GitLab Monitor] Static fix applied")
            else:
                print(
                    "[GitLab Monitor] Static fix did not converge; "
                    "committing best effort"
                )
                self_heal_retry_notes.append(
                    f"Attempt {heal_attempt + 1}: static validation fix did not converge."
                )
                new_gitlab_ci = static_fix.get('gitlab_ci') or current_gitlab_ci
                new_dockerfile = static_fix.get('dockerfile') or current_dockerfile

        # Idempotency guard — skip the commit if nothing actually changed.
        if (
            new_gitlab_ci.strip() == current_gitlab_ci.strip()
            and new_dockerfile.strip() == current_dockerfile.strip()
        ):
            print("[GitLab Monitor] No diff in fixed files; retrying if attempts remain")
            self_heal_retry_notes.append(
                f"Attempt {heal_attempt + 1}: LLM/static fixer produced no file changes. "
                "The next attempt must change .gitlab-ci.yml or Dockerfile based on the real job log."
            )
            if project_id:
                progress_store.update(
                    project_id, branch, "build_running",
                    f"Self-heal attempt {heal_attempt + 1}/{max_heal_attempts} "
                    "produced no changes. Retrying with stronger context...",
                    attempt=heal_attempt + 1,
                )
            await asyncio.sleep(2)
            continue

        # Final guardrail pass after any LLM self-heal response. The fixer can
        # reintroduce upload blocks or less reliable Kaniko auth syntax even
        # when initial generation was clean.
        new_gitlab_ci = pipeline_generator._validate_and_fix_pipeline(
            new_gitlab_ci,
            current_gitlab_ci,
        )
        new_gitlab_ci = pipeline_generator._ensure_learn_stage(new_gitlab_ci)
        new_gitlab_ci, new_dockerfile, img_corrections = (
            pipeline_generator.validate_and_fix_pipeline_images(
                new_gitlab_ci,
                new_dockerfile,
                language,
            )
        )
        if img_corrections:
            print(f"[GitLab Monitor] Final image guardrails applied: {img_corrections}")

        # Auto-seed any newly referenced images BEFORE pushing the commit
        try:
            print("[GitLab Monitor] Re-seeding images for self-heal commit...")
            await ensure_images_in_nexus(new_gitlab_ci)
        except Exception as seed_err:
            print(f"[GitLab Monitor] Image seeding warning: {seed_err}")

        previous_max_pipeline_id = last_pipeline_id

        try:
            if project_id:
                progress_store.update(
                    project_id, branch, "build_running",
                    f"Committing self-heal fix {heal_attempt + 1}/{max_heal_attempts}...",
                    attempt=heal_attempt + 1,
                )

            await pipeline_generator.commit_to_gitlab(
                repo_url=repo_url,
                gitlab_token=gitlab_token,
                files={
                    ".gitlab-ci.yml": new_gitlab_ci,
                    "Dockerfile": new_dockerfile,
                },
                branch_name=branch,
                # Consistent "AI pipeline run · ... attempt N" label so the
                # GitLab pipeline list reads naturally:
                #   attempt 1   AI pipeline run · LLM-generated · attempt 1
                #   attempt 2   AI pipeline run · self-heal attempt 1/10
                #   attempt 3   AI pipeline run · self-heal attempt 2/10
                commit_message=(
                    f"AI pipeline run · self-heal attempt "
                    f"{heal_attempt + 1}/{max_heal_attempts} [AI Generated]"
                ),
            )
            current_gitlab_ci = new_gitlab_ci
            current_dockerfile = new_dockerfile
            print(
                f"[GitLab Monitor] Self-heal commit "
                f"#{heal_attempt + 1} pushed to {branch}"
            )
            # Give GitLab a moment to register the new pipeline
            await asyncio.sleep(10)
        except Exception as commit_err:
            print(f"[GitLab Monitor] Self-heal commit error: {commit_err}")
            if project_id:
                progress_store.complete(
                    project_id, branch, "failed",
                    f"Self-healing commit failed: {commit_err}",
                )
            return


async def _monitor_pipeline_safely(**kwargs):
    """Run the long GitLab monitor detached from the HTTP response."""
    project_id = kwargs.get("project_id")
    branch = kwargs.get("branch")
    try:
        await monitor_pipeline_with_self_heal(**kwargs)
    except Exception as exc:
        print(f"[GitLab Monitor] Background monitor failed for {branch}: {exc}")
        if project_id and branch:
            progress_store.complete(
                project_id,
                branch,
                "failed",
                f"Monitor failed: {exc}",
            )


async def _run_self_heal(
    repo_url: str,
    gitlab_token: str,
    additional_context: str,
    auto_commit: bool,
    max_attempts: int = 10,
    force_llm: bool = True,
):
    """Background task variant of ``/self-heal`` — pre-commit fix loop."""
    try:
        result = await pipeline_generator.generate_pipeline_files(
            repo_url=repo_url,
            gitlab_token=gitlab_token,
            additional_context=additional_context,
            use_template_only=False,
            force_llm=force_llm,
        )

        analysis = result.get('analysis', {})
        parsed = pipeline_generator.parse_gitlab_url(repo_url)
        project_path = parsed.get('path', '')

        fix_result = await gitlab_llm_fixer.iterative_fix(
            gitlab_ci=result['gitlab_ci'],
            dockerfile=result['dockerfile'],
            validator=gitlab_dry_run_validator,
            analysis=analysis,
            gitlab_token=gitlab_token,
            project_path=project_path,
            max_attempts=max_attempts,
        )

        if auto_commit and fix_result.get('success'):
            try:
                await ensure_images_in_nexus(fix_result['gitlab_ci'])
            except Exception as seed_err:
                print(f"[GitLab Self-Heal] Image seed warning: {seed_err}")

            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            await pipeline_generator.commit_to_gitlab(
                repo_url=repo_url,
                gitlab_token=gitlab_token,
                files={
                    ".gitlab-ci.yml": fix_result['gitlab_ci'],
                    "Dockerfile": fix_result['dockerfile'],
                },
                branch_name=f"feature/ai-pipeline-selfheal-{ts}",
                commit_message="Add CI/CD pipeline (self-heal) [AI Generated]",
            )
            print(f"[GitLab Self-Heal] Committed fixed pipeline for {repo_url}")
        elif not fix_result.get('success'):
            print(
                f"[GitLab Self-Heal] Fix failed after "
                f"{fix_result.get('attempts')} attempts"
            )
    except Exception as e:
        print(f"[GitLab Self-Heal] Error: {e}")


# ============================================================================
# Request/Response Models
# ============================================================================

class GeneratePipelineRequest(BaseModel):
    repo_url: str = Field(..., description="GitLab repository URL")
    gitlab_token: str = Field(..., description="GitLab access token")
    additional_context: Optional[str] = Field(
        None, description="Additional requirements or context for generation"
    )
    model: str = Field(
        default="pipeline-generator-v5",
        description="LLM model to use for generation",
    )
    use_template_only: bool = Field(
        default=False,
        description="If True, skip LLM and use default templates directly",
    )
    force_llm: bool = Field(
        default=False,
        description="If True, skip direct ChromaDB template reuse and force LLM generation/self-heal",
    )
    progress_key: Optional[str] = Field(
        default=None,
        description=(
            "Optional key the generator uses to publish live phase updates "
            "to the shared chat-inflight store. The frontend polls "
            "GET /api/v1/chat/inflight/{progress_key} to render a live "
            "status card while generation is in flight."
        ),
    )
    pipeline_requirements: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Chatbot-confirmed pipeline requirements such as output mode, build tool, and artifact target.",
    )


class GeneratePipelineResponse(BaseModel):
    success: bool
    gitlab_ci: str
    dockerfile: str
    analysis: Dict[str, Any]
    model_used: str
    feedback_used: int
    template_source: Optional[str] = None
    # New fields exposing the RAG-first / LLM-fallback contract:
    source_token: Optional[str] = None
    rag_hit: bool = False
    had_rag_reference: bool = False
    fix_attempts: int = 0
    validation_passed: bool = False
    persisted_to_rag: bool = False
    final_errors: Optional[List[str]] = None


class CommitRequest(BaseModel):
    repo_url: str
    gitlab_token: str
    gitlab_ci: str
    dockerfile: str = ""
    branch_name: Optional[str] = Field(
        None, description="Branch name (auto-generated if not provided)"
    )
    commit_message: str = Field(
        default="Add CI/CD pipeline configuration [AI Generated]"
    )


class CommitResponse(BaseModel):
    success: bool
    commit_id: str
    branch: str
    web_url: Optional[str]
    project_id: int


class PipelineStatusRequest(BaseModel):
    repo_url: str
    gitlab_token: str
    branch: str


class FeedbackRequest(BaseModel):
    repo_url: str
    gitlab_token: str
    branch: str
    original_gitlab_ci: str
    original_dockerfile: str
    error_type: str = Field(..., description="Type of error that was fixed")
    fix_description: str = Field(..., description="Description of what was fixed")


class FullWorkflowRequest(BaseModel):
    repo_url: str
    gitlab_token: str
    additional_context: Optional[str] = None
    model: str = "pipeline-generator-v5"
    auto_commit: bool = False
    branch_name: Optional[str] = None
    use_template_only: bool = Field(
        default=False,
        description="If True, skip LLM and use default templates directly",
    )
    force_llm: bool = Field(
        default=False,
        description="If True, skip direct ChromaDB template reuse and force LLM generation/self-heal",
    )


class RecordPipelineResultRequest(BaseModel):
    repo_url: str
    gitlab_token: str
    branch: str
    pipeline_id: int


class StoreTemplateRequest(BaseModel):
    language: str
    framework: str = "generic"
    gitlab_ci: str
    dockerfile: Optional[str] = None
    description: Optional[str] = None


class SelfHealRequest(BaseModel):
    repo_url: str
    gitlab_token: str
    additional_context: Optional[str] = None
    auto_commit: bool = True
    max_attempts: int = 10
    force_llm: bool = True


class DryRunRequest(BaseModel):
    gitlab_ci: str
    dockerfile: str = ""
    gitlab_token: Optional[str] = None
    project_path: Optional[str] = None
    require_dockerfile: bool = True


class FixRequest(BaseModel):
    gitlab_ci: str
    dockerfile: str
    error_log: str
    job_name: Optional[str] = None
    language: Optional[str] = None
    framework: Optional[str] = None


class CommitAndMonitorRequest(BaseModel):
    repo_url: str
    gitlab_token: str
    gitlab_ci: str
    dockerfile: str = ""
    language: Optional[str] = "unknown"
    framework: Optional[str] = "generic"
    branch_name: Optional[str] = None
    commit_message: Optional[str] = None
    model_used: Optional[str] = None
    max_heal_attempts: int = 10
    rag_hit: bool = False


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/analyze")
async def analyze_repository(repo_url: str, gitlab_token: str):
    """Analyze a GitLab repository to detect language/framework/files."""
    try:
        analysis = await pipeline_generator.analyze_repository(repo_url, gitlab_token)
        return {"success": True, "analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate", response_model=GeneratePipelineResponse)
async def generate_pipeline(request: GeneratePipelineRequest):
    """Generate ``.gitlab-ci.yml`` and ``Dockerfile`` for a repository."""
    try:
        result = await pipeline_generator.generate_pipeline_files(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only,
            progress_key=request.progress_key,
            force_llm=request.force_llm,
            pipeline_requirements=request.pipeline_requirements,
        )

        return GeneratePipelineResponse(
            success=True,
            gitlab_ci=result['gitlab_ci'],
            dockerfile=result['dockerfile'],
            analysis=result['analysis'],
            model_used=result['model_used'],
            feedback_used=result.get('feedback_used', 0),
            template_source=result.get('template_source'),
            source_token=result.get('source_token'),
            rag_hit=bool(result.get('rag_hit')),
            had_rag_reference=bool(result.get('had_rag_reference')),
            fix_attempts=int(result.get('fix_attempts', 0)),
            validation_passed=bool(result.get('validation_passed')),
            persisted_to_rag=bool(result.get('persisted_to_rag')),
            final_errors=result.get('final_errors') or None,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit", response_model=CommitResponse)
async def commit_pipeline(request: CommitRequest):
    """Commit generated pipeline files to GitLab on a (possibly new) branch."""
    try:
        branch_name = request.branch_name
        if not branch_name:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            branch_name = f"feature/ai-pipeline-{timestamp}"

        files = {".gitlab-ci.yml": request.gitlab_ci}
        if request.dockerfile and request.dockerfile.strip():
            files["Dockerfile"] = request.dockerfile

        result = await pipeline_generator.commit_to_gitlab(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            files=files,
            branch_name=branch_name,
            commit_message=request.commit_message,
        )

        return CommitResponse(
            success=True,
            commit_id=result['commit_id'],
            branch=result['branch'],
            web_url=result.get('web_url'),
            project_id=result['project_id'],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/status")
async def get_pipeline_status(request: PipelineStatusRequest):
    """Get the latest pipeline status for a branch."""
    try:
        status = await pipeline_generator.get_pipeline_status(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            branch=request.branch,
        )
        return {"success": True, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def store_feedback(request: FeedbackRequest):
    """Store feedback from manual corrections for reinforcement learning."""
    try:
        differences = await pipeline_generator.compare_and_learn(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            branch=request.branch,
            generated_files={
                ".gitlab-ci.yml": request.original_gitlab_ci,
                "Dockerfile": request.original_dockerfile,
            },
        )

        gitlab_ci_diff = differences.get(".gitlab-ci.yml", {})
        dockerfile_diff = differences.get("Dockerfile", {})

        if gitlab_ci_diff.get("changed") or dockerfile_diff.get("changed"):
            analysis = await pipeline_generator.analyze_repository(
                request.repo_url, request.gitlab_token,
            )

            success = await pipeline_generator.store_feedback(
                original_gitlab_ci=request.original_gitlab_ci,
                corrected_gitlab_ci=gitlab_ci_diff.get(
                    "corrected", request.original_gitlab_ci
                ),
                original_dockerfile=request.original_dockerfile,
                corrected_dockerfile=dockerfile_diff.get(
                    "corrected", request.original_dockerfile
                ),
                language=analysis['language'],
                framework=analysis['framework'],
                error_type=request.error_type,
                fix_description=request.fix_description,
            )

            return {
                "success": success,
                "message": "Feedback stored for reinforcement learning",
                "changes_detected": {
                    "gitlab_ci": gitlab_ci_diff.get("changed", False),
                    "dockerfile": dockerfile_diff.get("changed", False),
                },
            }
        return {
            "success": True,
            "message": "No changes detected between original and current files",
            "changes_detected": {"gitlab_ci": False, "dockerfile": False},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedback/history")
async def get_feedback_history(
    language: Optional[str] = None,
    framework: Optional[str] = None,
    limit: int = 10,
):
    """Get stored feedback history."""
    try:
        feedback = await pipeline_generator.get_relevant_feedback(
            language=language or "",
            framework=framework or "",
            limit=limit,
        )
        return {"success": True, "feedback": feedback, "count": len(feedback)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Reinforcement Learning Endpoints
# ============================================================================

@router.post("/learn/record")
async def record_pipeline_result(request: RecordPipelineResultRequest):
    """Record the result of a pipeline for reinforcement learning."""
    try:
        result = await pipeline_generator.record_pipeline_result(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            branch=request.branch,
            pipeline_id=request.pipeline_id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/successful")
async def get_successful_pipelines(
    language: str,
    framework: Optional[str] = None,
    limit: int = 5,
):
    """Get successful pipeline configurations for a language/framework."""
    try:
        pipelines = await pipeline_generator.get_successful_pipelines(
            language=language,
            framework=framework or "",
            limit=limit,
        )
        return {
            "success": True,
            "language": language,
            "framework": framework,
            "pipelines": pipelines,
            "count": len(pipelines),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learn/best")
async def get_best_config(language: str, framework: Optional[str] = None):
    """Get the best performing pipeline configuration."""
    try:
        config = await pipeline_generator.get_best_pipeline_config(
            language=language,
            framework=framework or "",
        )
        if config:
            return {
                "success": True,
                "language": language,
                "framework": framework,
                "config": config,
                "source": "reinforcement_learning",
            }
        return {
            "success": True,
            "language": language,
            "framework": framework,
            "config": None,
            "message": (
                "No successful pipeline configurations found for this "
                "language/framework"
            ),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/learn/store-template")
async def store_template(request: StoreTemplateRequest):
    """Manually store a proven pipeline configuration."""
    try:
        success = await pipeline_generator.store_manual_template(
            language=request.language,
            framework=request.framework,
            gitlab_ci=request.gitlab_ci,
            dockerfile=request.dockerfile,
            description=request.description,
        )
        if success:
            return {
                "success": True,
                "message": (
                    f"Template stored successfully for "
                    f"{request.language}/{request.framework}"
                ),
                "language": request.language,
                "framework": request.framework,
            }
        raise HTTPException(status_code=500, detail="Failed to store template")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Self-healing & progress endpoints (mirror of GitHub side)
# ============================================================================

@router.get("/progress/{project_id}/{branch:path}")
async def get_pipeline_progress(project_id: int, branch: str):
    """Get real-time progress of GitLab pipeline monitoring + self-healing."""
    progress = progress_store.get(project_id, branch)
    if not progress:
        return {
            "found": False,
            "message": "No monitoring in progress for this pipeline",
        }
    return {"found": True, **progress.to_dict()}


@router.post("/self-heal")
async def self_heal_pipeline(request: SelfHealRequest):
    """Pre-commit self-healing pipeline: re-generate with LLM fix loop + commit."""
    try:
        result = await pipeline_generator.generate_pipeline_files(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            additional_context=request.additional_context or "",
            use_template_only=False,
            force_llm=request.force_llm,
        )

        gitlab_ci = result['gitlab_ci']
        dockerfile = result['dockerfile']
        analysis = result['analysis']
        parsed = pipeline_generator.parse_gitlab_url(request.repo_url)
        project_path = parsed.get('path', '')

        fix_result = await gitlab_llm_fixer.iterative_fix(
            gitlab_ci=gitlab_ci,
            dockerfile=dockerfile,
            validator=gitlab_dry_run_validator,
            analysis=analysis,
            gitlab_token=request.gitlab_token,
            project_path=project_path,
            max_attempts=request.max_attempts,
        )

        response = {
            "success": fix_result.get('success', False),
            "gitlab_ci": fix_result.get('gitlab_ci', gitlab_ci),
            "dockerfile": fix_result.get('dockerfile', dockerfile),
            "analysis": analysis,
            "fix_attempts": fix_result.get('attempts', 0),
            "fix_history": fix_result.get('fix_history', []),
        }

        if request.auto_commit and fix_result.get('success'):
            try:
                await ensure_images_in_nexus(fix_result['gitlab_ci'])
            except Exception as seed_err:
                print(f"[GitLab Self-Heal] Image seed warning: {seed_err}")

            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            commit_result = await pipeline_generator.commit_to_gitlab(
                repo_url=request.repo_url,
                gitlab_token=request.gitlab_token,
                files={
                    ".gitlab-ci.yml": fix_result['gitlab_ci'],
                    "Dockerfile": fix_result['dockerfile'],
                },
                branch_name=f"feature/ai-pipeline-selfheal-{ts}",
                commit_message="Add CI/CD pipeline (self-heal) [AI Generated]",
            )
            response['commit'] = commit_result

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/self-heal/async")
async def self_heal_pipeline_async(
    request: SelfHealRequest,
    background_tasks: BackgroundTasks,
):
    """Pre-commit self-healing pipeline — fire-and-forget background task."""
    try:
        background_tasks.add_task(
            _run_self_heal,
            request.repo_url,
            request.gitlab_token,
            request.additional_context or "",
            request.auto_commit,
            request.max_attempts,
            request.force_llm,
        )
        return {
            "success": True,
            "status": "started",
            "message": "Self-healing pipeline started in background",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dry-run")
async def dry_run_validation(request: DryRunRequest):
    """Validate ``.gitlab-ci.yml`` and ``Dockerfile`` before committing.

    Runs the full ``GitLabDryRunValidator`` (YAML lint, dockerfile syntax,
    structure check, GitLab CI Lint API server-side check when a project
    path + token is provided). Returns a structured per-check report so the
    caller can render which gate failed.
    """
    try:
        validator = gitlab_dry_run_validator
        results = await validator.validate_all(
            gitlab_ci=request.gitlab_ci,
            dockerfile=request.dockerfile,
            gitlab_token=request.gitlab_token,
            project_path=request.project_path,
            require_dockerfile=request.require_dockerfile,
        )
        all_valid, _ = validator.get_validation_summary(results)

        all_errors: List[str] = []
        all_warnings: List[str] = []
        for check_name, check_result in results.items():
            all_errors.extend([f"[{check_name}] {e}" for e in check_result.errors])
            all_warnings.extend([f"[{check_name}] {w}" for w in check_result.warnings])

        return {
            "success": True,
            "valid": all_valid,
            "errors": all_errors,
            "warnings": all_warnings,
            "results": {k: v.to_dict() for k, v in results.items()},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fix")
async def fix_pipeline_error(request: FixRequest):
    """Single-shot LLM fix from an error log (mirror of GitHub /fix)."""
    try:
        analysis = {
            "language": request.language or "unknown",
            "framework": request.framework or "generic",
            "package_manager": "unknown",
        }
        error_lines = [
            line.strip()
            for line in (request.error_log or "").split('\n')
            if line.strip()
        ]

        fix_result = await gitlab_llm_fixer.fix_pipeline(
            gitlab_ci=request.gitlab_ci,
            dockerfile=request.dockerfile,
            errors=error_lines,
            warnings=[],
            analysis=analysis,
        )
        return {
            "success": 'error' not in fix_result,
            "fixed_files": {
                "gitlab_ci": fix_result.get('gitlab_ci', request.gitlab_ci),
                "dockerfile": fix_result.get('dockerfile', request.dockerfile),
            },
            "error": fix_result.get('error'),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Workflow + commit-and-monitor endpoints
# ============================================================================

@router.post("/workflow")
async def full_workflow(
    request: FullWorkflowRequest,
    background_tasks: BackgroundTasks,
):
    """Complete workflow: analyze -> generate -> commit -> monitor.

    ``chromadb-direct`` RAG hits use ``monitor_pipeline_for_learning`` only
    (status polling, no RAG write, no LLM fixer). Non-RAG generations use
    ``monitor_pipeline_with_self_heal`` so a failed first pipeline can be
    corrected automatically. The response surfaces a ``monitoring`` block so
    the frontend can poll ``GET /pipeline/progress/{project_id}/{branch}``.
    """
    try:
        result = await pipeline_generator.generate_pipeline_files(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            additional_context=request.additional_context or "",
            model=request.model,
            use_template_only=request.use_template_only,
            force_llm=request.force_llm,
        )

        response: Dict[str, Any] = {
            "success": True,
            "generation": {
                "gitlab_ci": result['gitlab_ci'],
                "dockerfile": result['dockerfile'],
                "analysis": result['analysis'],
                "model_used": result['model_used'],
                "feedback_used": result.get('feedback_used', 0),
                "template_source": result.get('template_source'),
            },
            "commit": None,
            "monitoring": None,
        }

        if request.auto_commit:
            branch_name = request.branch_name
            if not branch_name:
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                branch_name = f"feature/ai-pipeline-{timestamp}"
            parsed = pipeline_generator.parse_gitlab_url(request.repo_url)
            existing_pipeline_id = await _latest_pipeline_id_for_ref(
                _gitlab_api_base(),
                _gitlab_headers(request.gitlab_token),
                parsed.get('project_path', ''),
                branch_name,
            )

            # Auto-seed images BEFORE committing so the pipeline has them
            try:
                await ensure_images_in_nexus(result['gitlab_ci'])
            except Exception as seed_err:
                print(f"[GitLab Workflow] Image seed warning: {seed_err}")

            files = {".gitlab-ci.yml": result['gitlab_ci']}
            if result.get('dockerfile'):
                files["Dockerfile"] = result['dockerfile']

            commit_result = await pipeline_generator.commit_to_gitlab(
                repo_url=request.repo_url,
                gitlab_token=request.gitlab_token,
                files=files,
                branch_name=branch_name,
                commit_message="Add CI/CD pipeline configuration [AI Generated]",
            )

            response["commit"] = {
                "branch": commit_result['branch'],
                "commit_id": commit_result['commit_id'],
                "web_url": commit_result.get('web_url'),
                "project_id": commit_result['project_id'],
            }

            is_rag_direct = (
                bool(result.get('rag_hit'))
                or result.get('model_used') in ('chromadb-direct', 'direct-artifact-template')
            )

            # RAG-direct runs use a status-only monitor. The LLM self-heal
            # loop is reserved for pipelines generated outside RAG.
            project_id_int = int(commit_result['project_id'])
            prog = progress_store.create(
                project_id=project_id_int,
                branch=branch_name,
                max_attempts=0 if is_rag_direct else 10,
            )
            prog.model_used = result.get('model_used', 'unknown')

            if is_rag_direct:
                progress_store.update(
                    project_id_int, branch_name, "monitoring",
                    "RAG template committed. Status-only monitor active; "
                    "no LLM/self-heal path is running.",
                )
                asyncio.create_task(monitor_pipeline_for_learning(
                    repo_url=request.repo_url,
                    gitlab_token=request.gitlab_token,
                    branch=branch_name,
                    project_id=project_id_int,
                    previous_max_pipeline_id=existing_pipeline_id,
                ))
            else:
                asyncio.create_task(_monitor_pipeline_safely(
                    repo_url=request.repo_url,
                    gitlab_token=request.gitlab_token,
                    branch=branch_name,
                    project_id=project_id_int,
                    gitlab_ci=result['gitlab_ci'],
                    dockerfile=result['dockerfile'],
                    language=result.get('analysis', {}).get('language', 'unknown'),
                    framework=result.get('analysis', {}).get('framework', 'generic'),
                    previous_max_pipeline_id=existing_pipeline_id,
                ))

            response["monitoring"] = {
                "status": "scheduled",
                "project_id": project_id_int,
                "branch": branch_name,
                "rl_enabled": not is_rag_direct,
                "self_healing_enabled": not is_rag_direct,
                "monitor_mode": "rag_status_only" if is_rag_direct else "self_heal_on_failure",
            }

        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commit-and-monitor")
async def commit_and_monitor(
    request: CommitAndMonitorRequest,
    background_tasks: BackgroundTasks,
):
    """Auto-seed images, commit pipeline files, then self-heal monitor.

    This is the endpoint the chat tool calls when the user says "commit and
    run". Returns immediately with the commit metadata; monitoring runs in
    the background and surfaces via ``progress_store``.
    """
    try:
        branch_name = request.branch_name
        if not branch_name:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            branch_name = f"feature/ai-pipeline-{timestamp}"
        parsed = pipeline_generator.parse_gitlab_url(request.repo_url)
        existing_pipeline_id = await _latest_pipeline_id_for_ref(
            _gitlab_api_base(),
            _gitlab_headers(request.gitlab_token),
            parsed.get('project_path', ''),
            branch_name,
        )

        # Step 1: auto-seed any referenced images
        try:
            await ensure_images_in_nexus(request.gitlab_ci)
        except Exception as seed_err:
            print(f"[GitLab Commit+Monitor] Image seed warning: {seed_err}")

        # Step 2: commit
        files = {".gitlab-ci.yml": request.gitlab_ci}
        if request.dockerfile and request.dockerfile.strip():
            files["Dockerfile"] = request.dockerfile

        commit_result = await pipeline_generator.commit_to_gitlab(
            repo_url=request.repo_url,
            gitlab_token=request.gitlab_token,
            files=files,
            branch_name=branch_name,
            commit_message=(
                request.commit_message
                or "Add CI/CD pipeline configuration [AI Generated]"
            ),
        )

        # Step 3: progress entry + monitor. RAG-direct runs must stay out of
        # the LLM self-heal path; they only need status polling.
        is_rag_direct = (
            bool(request.rag_hit)
            or request.model_used in ('chromadb-direct', 'direct-artifact-template')
        )
        project_id_int = int(commit_result['project_id'])
        prog = progress_store.create(
            project_id=project_id_int,
            branch=commit_result['branch'],
            max_attempts=0 if is_rag_direct else request.max_heal_attempts,
        )
        if request.model_used:
            prog.model_used = request.model_used

        if is_rag_direct:
            progress_store.update(
                project_id_int, commit_result['branch'], "monitoring",
                "RAG template committed. Status-only monitor active; "
                "no LLM/self-heal path is running.",
            )
            asyncio.create_task(monitor_pipeline_for_learning(
                repo_url=request.repo_url,
                gitlab_token=request.gitlab_token,
                branch=commit_result['branch'],
                project_id=project_id_int,
                previous_max_pipeline_id=existing_pipeline_id,
            ))
        else:
            asyncio.create_task(_monitor_pipeline_safely(
                repo_url=request.repo_url,
                gitlab_token=request.gitlab_token,
                branch=commit_result['branch'],
                project_id=project_id_int,
                gitlab_ci=request.gitlab_ci,
                dockerfile=request.dockerfile,
                language=request.language or 'unknown',
                framework=request.framework or 'generic',
                max_heal_attempts=request.max_heal_attempts,
                previous_max_pipeline_id=existing_pipeline_id,
            ))

        return {
            "success": True,
            "branch": commit_result['branch'],
            "commit_id": commit_result['commit_id'],
            "project_id": project_id_int,
            "web_url": commit_result.get('web_url'),
            "monitoring": {
                "project_id": project_id_int,
                "branch": commit_result['branch'],
                "rl_enabled": not is_rag_direct,
                "self_healing_enabled": not is_rag_direct,
                "max_heal_attempts": 0 if is_rag_direct else request.max_heal_attempts,
                "monitor_mode": "rag_status_only" if is_rag_direct else "self_heal_on_failure",
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
