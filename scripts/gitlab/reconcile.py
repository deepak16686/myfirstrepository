#!/usr/bin/env python3
"""
reconcile.py
------------

Cross-reference a local workspace inventory (produced by discover_local_repos.sh)
against the projects owned by a user on a self-hosted GitLab instance and
report on:

  MATCHED           - local repo's origin URL resolves to a GitLab project that
                      exists.
  MISSING_ON_GITLAB - local repo's origin URL points at this GitLab host but
                      the project is 404 on the API (it was deleted or never
                      finished pushing).
  ORPHAN_ON_GITLAB  - GitLab project exists but no local clone under the
                      workspace has its URL as origin (nothing lost, but the
                      operator should know about it).
  LOCAL_ONLY        - local repo has no GitLab origin at all (lives on GitHub,
                      Gitea, or is purely local).

Usage:
    python reconcile.py \
        --inventory inventory.json \
        --gitlab http://localhost:8929 \
        --token "$GITLAB_TOKEN" \
        [--dry-run] [--push-missing] [--force-dirty] [--yes] \
        [--verbose] [--json-report report.json]

Safety invariants:
  * NEVER deletes anything on GitLab.
  * NEVER pushes with --force.
  * Refuses to push a repo that has uncommitted changes unless --force-dirty.
  * --push-missing prompts "Continue? [y/N]" once unless --yes is passed.
  * The PAT is redacted from every log line.
  * The default mode is --dry-run (report only).

Requires:
  * Python 3.9+
  * httpx  (pip install httpx)
  * git    (on PATH)

The script is deliberately dependency-light and self-contained.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse

try:
    import httpx  # type: ignore
except ImportError as exc:  # pragma: no cover - import-time only
    sys.stderr.write(
        "ERROR: httpx is required. Install with: pip install httpx\n"
    )
    raise SystemExit(2) from exc


# ---------------------------------------------------------------------------
# Logging (PAT-safe)
# ---------------------------------------------------------------------------

_REDACT_PATTERNS = [
    re.compile(r"(PRIVATE-TOKEN:\s*)[A-Za-z0-9_\-]+", re.IGNORECASE),
    re.compile(r"(private_token=)[A-Za-z0-9_\-]+", re.IGNORECASE),
    re.compile(r"(access_token=)[A-Za-z0-9_\-]+", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    # glpat- tokens in plain text
    re.compile(r"glpat-[A-Za-z0-9_\-]+"),
]


class RedactingFormatter(logging.Formatter):
    """Formatter that strips anything that looks like a GitLab PAT."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pat in _REDACT_PATTERNS:
            msg = pat.sub(
                lambda m: (m.group(1) + "***REDACTED***")
                if m.groups()
                else "***REDACTED***",
                msg,
            )
        return msg


def _setup_logging(verbose: bool) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        RedactingFormatter("[reconcile] %(levelname)s %(message)s")
    )
    logger = logging.getLogger("gitlab.reconcile")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LocalRepo:
    path: str
    remotes: dict[str, str]
    default_branch: str
    head: str
    clean: bool
    uncommitted_files: int

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "LocalRepo":
        return cls(
            path=str(obj["path"]),
            remotes={str(k): str(v) for k, v in dict(obj.get("remotes", {})).items()},
            default_branch=str(obj.get("default_branch", "")),
            head=str(obj.get("head", "")),
            clean=bool(obj.get("clean", False)),
            uncommitted_files=int(obj.get("uncommitted_files", 0)),
        )

    @property
    def origin(self) -> str | None:
        return self.remotes.get("origin")


@dataclass(frozen=True)
class GitLabProject:
    id: int
    path_with_namespace: str
    http_url_to_repo: str
    ssh_url_to_repo: str
    default_branch: str | None
    empty_repo: bool

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "GitLabProject":
        return cls(
            id=int(obj["id"]),
            path_with_namespace=str(obj["path_with_namespace"]),
            http_url_to_repo=str(obj.get("http_url_to_repo", "")),
            ssh_url_to_repo=str(obj.get("ssh_url_to_repo", "")),
            default_branch=(obj.get("default_branch") or None),
            empty_repo=bool(obj.get("empty_repo", False)),
        )


@dataclass
class Report:
    matched: list[dict[str, Any]] = field(default_factory=list)
    missing_on_gitlab: list[dict[str, Any]] = field(default_factory=list)
    orphan_on_gitlab: list[dict[str, Any]] = field(default_factory=list)
    local_only: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "matched": len(self.matched),
                "missing_on_gitlab": len(self.missing_on_gitlab),
                "orphan_on_gitlab": len(self.orphan_on_gitlab),
                "local_only": len(self.local_only),
                "actions": len(self.actions),
            },
            "matched": self.matched,
            "missing_on_gitlab": self.missing_on_gitlab,
            "orphan_on_gitlab": self.orphan_on_gitlab,
            "local_only": self.local_only,
            "actions": self.actions,
        }


# ---------------------------------------------------------------------------
# URL normalization
# ---------------------------------------------------------------------------


def normalize_gitlab_base(url: str) -> str:
    """Normalize a GitLab base URL: strip trailing slash, force scheme."""
    p = urlparse(url)
    if not p.scheme:
        p = urlparse("http://" + url)
    path = p.path.rstrip("/")
    return urlunparse((p.scheme, p.netloc, path, "", "", ""))


def remote_is_gitlab_host(remote_url: str, gitlab_base: str) -> bool:
    """True iff remote_url targets the same host:port as gitlab_base.

    Supports both http(s)://host[:port]/path.git and
    git@host:group/name.git SSH forms.
    """
    if not remote_url:
        return False

    base = urlparse(gitlab_base)
    base_host = (base.hostname or "").lower()
    base_port = base.port
    base_netloc = base_host + (f":{base_port}" if base_port else "")

    # SSH form: git@host:group/name.git
    if remote_url.startswith("git@") or "@" in remote_url.split(":", 1)[0]:
        # e.g. git@gitlab.local:root/thing.git
        try:
            _, rest = remote_url.split("@", 1)
            host_part = rest.split(":", 1)[0].lower()
            return host_part == base_host
        except ValueError:
            return False

    # HTTP(S) form
    p = urlparse(remote_url)
    remote_host = (p.hostname or "").lower()
    remote_port = p.port
    remote_netloc = remote_host + (f":{remote_port}" if remote_port else "")
    if remote_host == base_host and (base_port is None or remote_port == base_port):
        return True
    # Also allow exact netloc match if one side omits the default port.
    return remote_netloc == base_netloc


def path_with_namespace_from_remote(
    remote_url: str, gitlab_base: str
) -> str | None:
    """Extract "<group>/<project>" from a GitLab remote URL."""
    if not remote_url:
        return None

    # SSH form
    if "@" in remote_url and remote_url.startswith("git@"):
        try:
            _, rest = remote_url.split(":", 1)
            return rest.removesuffix(".git").strip("/")
        except ValueError:
            return None

    p = urlparse(remote_url)
    if not p.path:
        return None
    path = p.path.strip("/").removesuffix(".git")
    return path or None


# ---------------------------------------------------------------------------
# GitLab API client
# ---------------------------------------------------------------------------


class GitLabClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        logger: logging.Logger,
        timeout: float = 30.0,
        max_retries: int = 5,
    ) -> None:
        self.base = normalize_gitlab_base(base_url)
        self.token = token
        self.log = logger
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.Client(
            base_url=f"{self.base}/api/v4",
            headers={
                "PRIVATE-TOKEN": token,
                "Accept": "application/json",
                "User-Agent": "gitlab-reconcile/1.0",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitLabClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- low-level request with 429/5xx retry -------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> tuple[int, Any, httpx.Headers]:
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._client.request(
                    method, path, params=params, json=json_body
                )
            except httpx.TransportError as e:
                if attempt >= self.max_retries:
                    raise
                backoff = min(30.0, 2.0 ** attempt)
                self.log.warning(
                    "transport error on %s %s: %s; retrying in %.1fs",
                    method,
                    path,
                    e,
                    backoff,
                )
                time.sleep(backoff)
                continue

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "5"))
                self.log.warning(
                    "rate-limited (429) on %s %s; sleeping %.1fs",
                    method,
                    path,
                    retry_after,
                )
                time.sleep(retry_after)
                if attempt >= self.max_retries:
                    return resp.status_code, None, resp.headers
                continue

            if 500 <= resp.status_code < 600 and attempt < self.max_retries:
                backoff = min(30.0, 2.0 ** attempt)
                self.log.warning(
                    "server error %s on %s %s; retrying in %.1fs",
                    resp.status_code,
                    method,
                    path,
                    backoff,
                )
                time.sleep(backoff)
                continue

            body: Any
            if expect_json and resp.content:
                try:
                    body = resp.json()
                except json.JSONDecodeError:
                    body = resp.text
            else:
                body = resp.text
            return resp.status_code, body, resp.headers

    # -- high-level helpers -------------------------------------------------
    def list_owned_projects(self) -> list[GitLabProject]:
        """Paginate GET /projects?owned=true&per_page=100."""
        projects: list[GitLabProject] = []
        page = 1
        per_page = 100
        while True:
            status, body, headers = self._request(
                "GET",
                "/projects",
                params={
                    "owned": "true",
                    "per_page": str(per_page),
                    "page": str(page),
                    "simple": "false",
                },
            )
            if status != 200 or not isinstance(body, list):
                raise RuntimeError(
                    f"GitLab /projects returned HTTP {status}: "
                    f"{str(body)[:200]}"
                )
            for obj in body:
                try:
                    projects.append(GitLabProject.from_json(obj))
                except (KeyError, ValueError) as e:
                    self.log.warning("malformed project skipped: %s", e)
            next_page = headers.get("X-Next-Page", "").strip()
            if not next_page:
                break
            page = int(next_page)
        return projects

    def get_project(self, path_with_namespace: str) -> GitLabProject | None:
        # URL-encode the slashes in path_with_namespace per GitLab API.
        from urllib.parse import quote as _q

        status, body, _ = self._request(
            "GET", f"/projects/{_q(path_with_namespace, safe='')}"
        )
        if status == 404:
            return None
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError(
                f"GitLab /projects/{path_with_namespace} returned HTTP {status}"
            )
        return GitLabProject.from_json(body)

    def create_project(
        self,
        name: str,
        *,
        namespace_id: int | None = None,
        default_branch: str | None = None,
        visibility: str = "private",
    ) -> GitLabProject:
        payload: dict[str, Any] = {
            "name": name,
            "path": name,
            "visibility": visibility,
            "initialize_with_readme": False,
        }
        if namespace_id is not None:
            payload["namespace_id"] = namespace_id
        if default_branch:
            payload["default_branch"] = default_branch

        status, body, _ = self._request(
            "POST", "/projects", json_body=payload
        )
        if status not in (200, 201) or not isinstance(body, dict):
            raise RuntimeError(
                f"POST /projects failed: HTTP {status}: {str(body)[:200]}"
            )
        return GitLabProject.from_json(body)

    def current_user(self) -> dict[str, Any]:
        status, body, _ = self._request("GET", "/user")
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError(f"GET /user failed: HTTP {status}")
        return body


# ---------------------------------------------------------------------------
# git subprocess helpers (no secret leakage)
# ---------------------------------------------------------------------------


def run_git(
    args: list[str],
    *,
    cwd: str,
    logger: logging.Logger,
    check: bool = True,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = ["git", *args]
    logger.debug("git(%s) %s", cwd, " ".join(shlex.quote(a) for a in args))
    env = os.environ.copy()
    # Never let git prompt interactively in automation.
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}: "
            f"rc={proc.returncode} stderr={proc.stderr.strip()[:400]}"
        )
    return proc


# ---------------------------------------------------------------------------
# Reconcile logic
# ---------------------------------------------------------------------------


def classify(
    local_repos: list[LocalRepo],
    gitlab_projects: list[GitLabProject],
    gitlab_base: str,
    logger: logging.Logger,
) -> Report:
    report = Report()

    projects_by_pwn: dict[str, GitLabProject] = {
        p.path_with_namespace.lower(): p for p in gitlab_projects
    }
    projects_seen_by_local: set[str] = set()

    for lr in local_repos:
        origin = lr.origin
        if not origin:
            report.local_only.append(
                {
                    "path": lr.path,
                    "reason": "no origin remote",
                    "other_remotes": list(lr.remotes.keys()),
                }
            )
            continue

        if not remote_is_gitlab_host(origin, gitlab_base):
            report.local_only.append(
                {
                    "path": lr.path,
                    "origin": origin,
                    "reason": "origin does not point at target GitLab host",
                }
            )
            continue

        pwn = path_with_namespace_from_remote(origin, gitlab_base)
        if not pwn:
            report.local_only.append(
                {
                    "path": lr.path,
                    "origin": origin,
                    "reason": "could not parse path_with_namespace from origin",
                }
            )
            continue

        project = projects_by_pwn.get(pwn.lower())
        if project is None:
            report.missing_on_gitlab.append(
                {
                    "path": lr.path,
                    "origin": origin,
                    "expected_path_with_namespace": pwn,
                    "default_branch": lr.default_branch,
                    "head": lr.head,
                    "clean": lr.clean,
                    "uncommitted_files": lr.uncommitted_files,
                }
            )
        else:
            projects_seen_by_local.add(project.path_with_namespace.lower())
            report.matched.append(
                {
                    "path": lr.path,
                    "origin": origin,
                    "project_id": project.id,
                    "path_with_namespace": project.path_with_namespace,
                    "default_branch_local": lr.default_branch,
                    "default_branch_gitlab": project.default_branch,
                    "empty_repo_on_gitlab": project.empty_repo,
                    "clean": lr.clean,
                    "uncommitted_files": lr.uncommitted_files,
                }
            )

    for p in gitlab_projects:
        if p.path_with_namespace.lower() in projects_seen_by_local:
            continue
        report.orphan_on_gitlab.append(
            {
                "project_id": p.id,
                "path_with_namespace": p.path_with_namespace,
                "http_url_to_repo": p.http_url_to_repo,
                "default_branch": p.default_branch,
                "empty_repo": p.empty_repo,
            }
        )

    logger.info(
        "classification: matched=%d missing=%d orphan=%d local_only=%d",
        len(report.matched),
        len(report.missing_on_gitlab),
        len(report.orphan_on_gitlab),
        len(report.local_only),
    )
    return report


# ---------------------------------------------------------------------------
# Push-missing workflow
# ---------------------------------------------------------------------------


def confirm(prompt: str) -> bool:
    try:
        resp = input(prompt).strip().lower()
    except EOFError:
        return False
    return resp in ("y", "yes")


def push_missing(
    report: Report,
    client: GitLabClient,
    *,
    user_namespace_id: int,
    force_dirty: bool,
    logger: logging.Logger,
) -> None:
    if not report.missing_on_gitlab:
        logger.info("nothing to push: missing_on_gitlab is empty")
        return

    for entry in list(report.missing_on_gitlab):
        path = entry["path"]
        pwn = entry["expected_path_with_namespace"]
        default_branch = entry.get("default_branch") or "main"
        clean = bool(entry.get("clean", False))
        uncommitted = int(entry.get("uncommitted_files", 0))
        action: dict[str, Any] = {
            "path": path,
            "path_with_namespace": pwn,
            "default_branch": default_branch,
            "steps": [],
            "status": "pending",
        }

        if not clean and not force_dirty:
            action["status"] = "skipped_dirty"
            action["reason"] = (
                f"uncommitted files={uncommitted}; re-run with --force-dirty"
            )
            logger.warning(
                "skip %s: %d uncommitted files (pass --force-dirty to override)",
                path,
                uncommitted,
            )
            report.actions.append(action)
            continue

        # 1) create project
        name = pwn.rsplit("/", 1)[-1]
        try:
            project = client.create_project(
                name=name,
                namespace_id=user_namespace_id,
                default_branch=default_branch,
                visibility="private",
            )
            action["steps"].append(
                {
                    "step": "create_project",
                    "status": "ok",
                    "project_id": project.id,
                    "path_with_namespace": project.path_with_namespace,
                }
            )
            logger.info(
                "created GitLab project %s (id=%d)",
                project.path_with_namespace,
                project.id,
            )
        except Exception as e:
            action["status"] = "failed_create"
            action["steps"].append(
                {"step": "create_project", "status": "failed", "error": str(e)}
            )
            logger.error("failed to create project for %s: %s", path, e)
            report.actions.append(action)
            continue

        # 2) git push --all (NEVER --force)
        try:
            run_git(
                ["push", "origin", "--all"],
                cwd=path,
                logger=logger,
            )
            action["steps"].append(
                {"step": "push_all_branches", "status": "ok"}
            )
        except Exception as e:
            action["status"] = "failed_push_branches"
            action["steps"].append(
                {"step": "push_all_branches", "status": "failed", "error": str(e)}
            )
            logger.error("failed to push branches from %s: %s", path, e)
            report.actions.append(action)
            continue

        # 3) git push --tags
        try:
            run_git(
                ["push", "origin", "--tags"],
                cwd=path,
                logger=logger,
            )
            action["steps"].append({"step": "push_tags", "status": "ok"})
        except Exception as e:
            action["status"] = "failed_push_tags"
            action["steps"].append(
                {"step": "push_tags", "status": "failed", "error": str(e)}
            )
            logger.error("failed to push tags from %s: %s", path, e)
            report.actions.append(action)
            continue

        action["status"] = "ok"
        report.actions.append(action)


# ---------------------------------------------------------------------------
# Pretty-print
# ---------------------------------------------------------------------------


def print_report(report: Report, stream: Any = sys.stdout) -> None:
    def _write(s: str = "") -> None:
        stream.write(s + "\n")

    d = report.as_dict()
    _write("=" * 72)
    _write("GitLab Reconciliation Report")
    _write("=" * 72)
    _write(f"  MATCHED:           {d['summary']['matched']}")
    _write(f"  MISSING_ON_GITLAB: {d['summary']['missing_on_gitlab']}")
    _write(f"  ORPHAN_ON_GITLAB:  {d['summary']['orphan_on_gitlab']}")
    _write(f"  LOCAL_ONLY:        {d['summary']['local_only']}")
    _write("-" * 72)

    if report.matched:
        _write("MATCHED (local <-> GitLab):")
        for m in report.matched:
            dirty = "" if m.get("clean") else f"  [DIRTY uncommitted={m.get('uncommitted_files')}]"
            _write(f"  [OK]    {m['path']}")
            _write(
                f"          -> {m['path_with_namespace']} "
                f"(id={m['project_id']}, default={m.get('default_branch_gitlab')}){dirty}"
            )
        _write("")

    if report.missing_on_gitlab:
        _write("MISSING_ON_GITLAB (local origin -> 404 on GitLab):")
        for m in report.missing_on_gitlab:
            _write(f"  [MISS]  {m['path']}")
            _write(
                f"          origin={m['origin']} "
                f"expected={m['expected_path_with_namespace']} "
                f"branch={m['default_branch']} "
                f"clean={m['clean']}"
            )
        _write("")

    if report.orphan_on_gitlab:
        _write("ORPHAN_ON_GITLAB (on GitLab but no local clone references it):")
        for o in report.orphan_on_gitlab:
            _write(
                f"  [ORPH]  {o['path_with_namespace']} "
                f"(id={o['project_id']}, default={o.get('default_branch')})"
            )
        _write("")

    if report.local_only:
        _write("LOCAL_ONLY (origin does not point at this GitLab host):")
        for lo in report.local_only:
            _write(f"  [LOCL]  {lo['path']}  ({lo.get('reason','')})")
        _write("")

    if report.actions:
        _write("ACTIONS TAKEN:")
        for a in report.actions:
            _write(
                f"  [{a['status'].upper()}] {a['path']} -> "
                f"{a['path_with_namespace']}"
            )
            for step in a.get("steps", []):
                _write(f"      - {step.get('step')}: {step.get('status')}")
        _write("")

    _write("=" * 72)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reconcile.py",
        description=(
            "Reconcile a local workspace inventory against a self-hosted "
            "GitLab instance. Reports MATCHED/MISSING/ORPHAN/LOCAL_ONLY and, "
            "optionally, recreates + pushes missing projects. Defaults to "
            "--dry-run (no writes)."
        ),
        epilog=(
            "Examples:\n"
            "  # Report only (safe):\n"
            "  python reconcile.py --inventory inv.json "
            "--gitlab http://localhost:8929 --token $GITLAB_TOKEN\n\n"
            "  # Recreate + push missing projects (prompts first):\n"
            "  python reconcile.py --inventory inv.json "
            "--gitlab http://localhost:8929 --token $GITLAB_TOKEN "
            "--push-missing\n\n"
            "  # Fully non-interactive push (CI):\n"
            "  python reconcile.py --inventory inv.json "
            "--gitlab http://localhost:8929 --token $GITLAB_TOKEN "
            "--push-missing --yes --force-dirty\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--inventory",
        required=True,
        help="Path to JSON produced by discover_local_repos.sh",
    )
    p.add_argument(
        "--gitlab",
        required=True,
        help="GitLab base URL, e.g. http://localhost:8929",
    )
    p.add_argument(
        "--token",
        default=os.environ.get("GITLAB_TOKEN", ""),
        help="GitLab PAT (api + write_repository). Defaults to $GITLAB_TOKEN.",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="(default) Report only. No writes to GitLab or git.",
    )
    mode.add_argument(
        "--push-missing",
        action="store_true",
        help=(
            "Create missing GitLab projects and push branches+tags. "
            "NEVER uses --force. Prompts once unless --yes is given."
        ),
    )
    p.add_argument(
        "--force-dirty",
        action="store_true",
        help="Allow pushing repos with uncommitted changes.",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt for --push-missing.",
    )
    p.add_argument(
        "--json-report",
        default=None,
        help="If set, write the machine-readable JSON report to this path.",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Debug-level logging.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logger = _setup_logging(args.verbose)

    if not args.token:
        logger.error(
            "no token: pass --token or set GITLAB_TOKEN "
            "(PAT scopes: api, write_repository)"
        )
        return 2

    inv_path = Path(args.inventory)
    if not inv_path.is_file():
        logger.error("inventory file not found: %s", inv_path)
        return 2
    try:
        raw = json.loads(inv_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error("inventory is not valid JSON: %s", e)
        return 2
    if not isinstance(raw, list):
        logger.error("inventory must be a JSON array")
        return 2

    local_repos = [LocalRepo.from_json(obj) for obj in raw]
    logger.info("loaded %d local repos from %s", len(local_repos), inv_path)

    gitlab_base = normalize_gitlab_base(args.gitlab)
    logger.info("GitLab base: %s", gitlab_base)

    with GitLabClient(gitlab_base, args.token, logger=logger) as client:
        try:
            user = client.current_user()
            user_id = int(user["id"])
            username = str(user.get("username", "?"))
            namespace_id = int(user.get("namespace_id") or user_id)
            logger.info(
                "authenticated as %s (user_id=%d, namespace_id=%d)",
                username,
                user_id,
                namespace_id,
            )
        except Exception as e:
            logger.error("failed to authenticate to GitLab: %s", e)
            return 3

        try:
            projects = client.list_owned_projects()
            logger.info("enumerated %d owned GitLab projects", len(projects))
        except Exception as e:
            logger.error("failed to list projects: %s", e)
            return 3

        report = classify(local_repos, projects, gitlab_base, logger)

        if args.push_missing:
            if not report.missing_on_gitlab:
                logger.info("no missing projects to push")
            else:
                if not args.yes:
                    logger.info(
                        "about to create %d GitLab project(s) and push from "
                        "local. This writes to GitLab.",
                        len(report.missing_on_gitlab),
                    )
                    for e in report.missing_on_gitlab:
                        logger.info(
                            "  * %s -> %s (branch=%s, clean=%s)",
                            e["path"],
                            e["expected_path_with_namespace"],
                            e["default_branch"],
                            e["clean"],
                        )
                    if not confirm("Continue? [y/N] "):
                        logger.warning("user aborted")
                        return 1
                push_missing(
                    report,
                    client,
                    user_namespace_id=namespace_id,
                    force_dirty=args.force_dirty,
                    logger=logger,
                )
        else:
            logger.info("dry-run mode: no writes performed")

    print_report(report, stream=sys.stdout)

    if args.json_report:
        Path(args.json_report).write_text(
            json.dumps(report.as_dict(), indent=2), encoding="utf-8"
        )
        logger.info("wrote JSON report to %s", args.json_report)

    # Exit code: 0 if everything matched OR dry-run, 4 if there are missing
    # repos and we did NOT push them, 5 if push attempts failed.
    if any(
        a.get("status", "").startswith("failed") for a in report.actions
    ):
        return 5
    if report.missing_on_gitlab and not args.push_missing:
        return 4
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
