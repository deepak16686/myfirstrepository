"""
File: service.py
Purpose: Fetches commit history from GitLab and Gitea repositories with date range filtering and URL auto-detection, translating between browser-facing URLs (localhost ports) and internal Docker DNS hostnames.
When Used: Called by the commit history router when users request commit logs, and by the release notes service to gather commits for changelog generation.
Why Created: Centralizes git commit retrieval logic that works across both GitLab and Gitea APIs, handling the URL translation layer (localhost:8929 to gitlab-server, localhost:3002 to gitea-server) needed in the Docker-based dev-stack environment.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from urllib.parse import urlparse, quote

import httpx

from app.config import settings
from app.services.pipeline.analyzer import parse_gitlab_url
from app.services.github_pipeline.analyzer import parse_github_url


class CommitHistoryService:
    """Service for fetching commit history from GitLab and Gitea repos."""

    def _to_internal_url(self, url: str) -> str:
        """Translate browser-facing URLs to internal Docker network URLs."""
        # Gitea: localhost:3002 -> gitea-server:3000
        url = url.replace("localhost:3002", "gitea-server:3000")
        # GitLab: localhost:8929 -> gitlab-server
        url = url.replace("localhost:8929", "gitlab-server")
        url = url.replace("localhost:18929", "prod-gitlab-server")
        url = url.replace("localhost:13002", "prod-gitea-server:3000")
        return url

    def _to_browser_url(self, url: str) -> str:
        """Translate internal Docker URLs to browser-facing URLs."""
        url = url.replace("gitea-server:3000", "localhost:3002")
        url = url.replace("gitlab-server", "localhost:8929")
        url = url.replace("prod-gitlab-server", "localhost:18929")
        url = url.replace("prod-gitea-server:3000", "localhost:13002")
        return url

    def _detect_server_type(self, repo_url: str) -> str:
        """Detect if URL points to GitLab or Gitea."""
        # Check after translating to internal URL so port-based detection works
        internal = self._to_internal_url(repo_url)
        parsed = urlparse(internal)
        gitlab_parsed = urlparse(settings.gitlab_url)

        if parsed.hostname == gitlab_parsed.hostname:
            return "gitlab"
        if parsed.hostname and "gitlab" in parsed.hostname:
            return "gitlab"
        return "gitea"

    def _get_default_token(self, server_type: str) -> Optional[str]:
        """Get the default token for the server type from settings."""
        if server_type == "gitlab":
            return settings.gitlab_token
        return settings.github_token

    async def get_branches(
        self,
        repo_url: str,
        token: Optional[str],
    ) -> Dict[str, Any]:
        """List all branches for a repository."""
        server_type = self._detect_server_type(repo_url)
        internal_url = self._to_internal_url(repo_url)
        effective_token = token or self._get_default_token(server_type)

        if not effective_token:
            return {"success": False, "error": f"No token provided and no default {server_type} token configured"}

        if server_type == "gitlab":
            return await self._fetch_gitlab_branches(internal_url, effective_token)
        return await self._fetch_gitea_branches(internal_url, effective_token)

    async def get_commits(
        self,
        repo_url: str,
        token: Optional[str],
        since: str,
        until: str,
        branch: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """Fetch commits from a repository within a date range."""
        server_type = self._detect_server_type(repo_url)
        internal_url = self._to_internal_url(repo_url)
        effective_token = token or self._get_default_token(server_type)

        if not effective_token:
            return {"success": False, "error": f"No token provided and no default {server_type} token configured"}

        if server_type == "gitlab":
            return await self._fetch_gitlab_commits(internal_url, effective_token, since, until, page, per_page, branch)
        return await self._fetch_gitea_commits(internal_url, effective_token, since, until, page, per_page, branch)

    async def get_commit_detail(
        self,
        repo_url: str,
        token: Optional[str],
        commit_sha: str,
    ) -> Dict[str, Any]:
        """Fetch a single commit with changed files."""
        server_type = self._detect_server_type(repo_url)
        internal_url = self._to_internal_url(repo_url)
        effective_token = token or self._get_default_token(server_type)

        if not effective_token:
            return {"success": False, "error": f"No token provided and no default {server_type} token configured"}

        if server_type == "gitlab":
            return await self._fetch_gitlab_commit_detail(internal_url, effective_token, commit_sha)
        return await self._fetch_gitea_commit_detail(internal_url, effective_token, commit_sha)

    # -------------------------------------------------------------------------
    # GitLab
    # -------------------------------------------------------------------------

    async def _fetch_gitlab_branches(
        self, repo_url: str, token: str
    ) -> Dict[str, Any]:
        parsed = parse_gitlab_url(repo_url)
        host = parsed["host"]
        project_path = parsed["project_path"]
        api_base = f"{host}/api/v4/projects/{project_path}"
        headers = {"PRIVATE-TOKEN": token}

        async with httpx.AsyncClient(timeout=30.0) as client:
            branches = []
            page = 1
            while True:
                resp = await client.get(
                    f"{api_base}/repository/branches",
                    headers=headers,
                    params={"page": page, "per_page": 100},
                )
                if resp.status_code != 200:
                    return {"success": False, "error": f"GitLab API error {resp.status_code}: {resp.text}"}
                batch = resp.json()
                if not batch:
                    break
                for b in batch:
                    branches.append({
                        "name": b["name"],
                        "default": b.get("default", False),
                    })
                if len(batch) < 100:
                    break
                page += 1

            return {"success": True, "server_type": "gitlab", "branches": branches}

    async def _fetch_gitlab_commits(
        self, repo_url: str, token: str, since: str, until: str, page: int, per_page: int,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed = parse_gitlab_url(repo_url)
        host = parsed["host"]
        project_path = parsed["project_path"]
        api_base = f"{host}/api/v4/projects/{project_path}"

        headers = {"PRIVATE-TOKEN": token}

        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "since": since,
                "until": until,
                "page": page,
                "per_page": per_page,
                "with_stats": "true",
            }
            if branch:
                params["ref_name"] = branch

            resp = await client.get(
                f"{api_base}/repository/commits",
                headers=headers,
                params=params,
            )
            if resp.status_code != 200:
                return {"success": False, "error": f"GitLab API error {resp.status_code}: {resp.text}"}

            raw_commits = resp.json()
            total = int(resp.headers.get("x-total", len(raw_commits)))

            # Build browser URL base
            browser_host = self._to_browser_url(host)
            commits = []
            for c in raw_commits:
                stats = c.get("stats") or {}
                commits.append({
                    "sha": c["id"],
                    "short_sha": c["short_id"],
                    "message": c["title"],
                    "author": c["author_name"],
                    "email": c.get("author_email", ""),
                    "date": c["created_at"],
                    "url": f"{browser_host}/{parsed['path']}/-/commit/{c['id']}",
                    "files_changed": stats.get("total", 0),
                    "additions": stats.get("additions", 0),
                    "deletions": stats.get("deletions", 0),
                })

            return {
                "success": True,
                "server_type": "gitlab",
                "repo": parsed["path"],
                "total": total,
                "page": page,
                "per_page": per_page,
                "commits": commits,
            }

    async def _fetch_gitlab_commit_detail(
        self, repo_url: str, token: str, commit_sha: str
    ) -> Dict[str, Any]:
        parsed = parse_gitlab_url(repo_url)
        host = parsed["host"]
        project_path = parsed["project_path"]
        api_base = f"{host}/api/v4/projects/{project_path}"

        headers = {"PRIVATE-TOKEN": token}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get commit details
            resp = await client.get(f"{api_base}/repository/commits/{commit_sha}", headers=headers)
            if resp.status_code != 200:
                return {"success": False, "error": f"GitLab API error {resp.status_code}: {resp.text}"}
            commit = resp.json()

            # Get diff to list changed files
            diff_resp = await client.get(f"{api_base}/repository/commits/{commit_sha}/diff", headers=headers)
            files = []
            if diff_resp.status_code == 200:
                for d in diff_resp.json():
                    added = d.get("diff", "").count("\n+") - 1  # rough count
                    removed = d.get("diff", "").count("\n-") - 1
                    if d.get("new_file"):
                        status = "added"
                    elif d.get("deleted_file"):
                        status = "removed"
                    elif d.get("renamed_file"):
                        status = "renamed"
                    else:
                        status = "modified"
                    files.append({
                        "filename": d.get("new_path", d.get("old_path", "")),
                        "old_filename": d.get("old_path", ""),
                        "status": status,
                        "additions": max(added, 0),
                        "deletions": max(removed, 0),
                    })

            stats = commit.get("stats") or {}
            return {
                "success": True,
                "sha": commit["id"],
                "short_sha": commit["short_id"],
                "message": commit["title"],
                "full_message": commit.get("message", ""),
                "author": commit["author_name"],
                "email": commit.get("author_email", ""),
                "date": commit["created_at"],
                "url": f"{self._to_browser_url(host)}/{parsed['path']}/-/commit/{commit['id']}",
                "stats": {
                    "additions": stats.get("additions", 0),
                    "deletions": stats.get("deletions", 0),
                    "total": stats.get("total", 0),
                },
                "files": files,
            }

    # -------------------------------------------------------------------------
    # Gitea
    # -------------------------------------------------------------------------

    async def _fetch_gitea_branches(
        self, repo_url: str, token: str
    ) -> Dict[str, Any]:
        parsed = parse_github_url(repo_url)
        host = parsed["host"]
        owner = parsed["owner"]
        repo = parsed["repo"]
        api_base = f"{host}/api/v1/repos/{owner}/{repo}"
        headers = {"Authorization": f"token {token}", "Accept": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            branches = []
            page = 1
            while True:
                resp = await client.get(
                    f"{api_base}/branches",
                    headers=headers,
                    params={"page": page, "limit": 50},
                )
                if resp.status_code != 200:
                    return {"success": False, "error": f"Gitea API error {resp.status_code}: {resp.text}"}
                batch = resp.json()
                if not batch:
                    break
                for b in batch:
                    branches.append({
                        "name": b["name"],
                        "default": b.get("name") == "main" or b.get("name") == "master",
                    })
                if len(batch) < 50:
                    break
                page += 1

            # Try to get the actual default branch from repo info
            repo_resp = await client.get(f"{api_base}", headers=headers)
            if repo_resp.status_code == 200:
                default_branch = repo_resp.json().get("default_branch", "")
                for br in branches:
                    br["default"] = br["name"] == default_branch

            return {"success": True, "server_type": "gitea", "branches": branches}

    async def _fetch_gitea_commits(
        self, repo_url: str, token: str, since: str, until: str, page: int, per_page: int,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        parsed = parse_github_url(repo_url)
        host = parsed["host"]
        owner = parsed["owner"]
        repo = parsed["repo"]
        api_base = f"{host}/api/v1/repos/{owner}/{repo}"

        headers = {"Authorization": f"token {token}", "Accept": "application/json"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "page": page,
                "limit": per_page,
            }
            if branch:
                params["sha"] = branch

            resp = await client.get(f"{api_base}/commits", headers=headers, params=params)
            if resp.status_code != 200:
                return {"success": False, "error": f"Gitea API error {resp.status_code}: {resp.text}"}

            raw_commits = resp.json()

            # Parse since/until for filtering
            since_dt = _parse_datetime(since)
            until_dt = _parse_datetime(until)

            # Build browser URL (translate internal host to browser host)
            browser_host = self._to_browser_url(host)

            commits = []
            for c in raw_commits:
                commit_info = c.get("commit", {})
                author_info = commit_info.get("author", {})
                commit_date_str = author_info.get("date", "")
                commit_dt = _parse_datetime(commit_date_str)

                # Date filter
                if commit_dt:
                    if since_dt and commit_dt < since_dt:
                        continue
                    if until_dt and commit_dt > until_dt:
                        continue

                sha = c.get("sha", "")
                stats = c.get("stats") or {}
                commits.append({
                    "sha": sha,
                    "short_sha": sha[:7],
                    "message": commit_info.get("message", "").split("\n")[0],
                    "author": author_info.get("name", ""),
                    "email": author_info.get("email", ""),
                    "date": commit_date_str,
                    "url": f"{browser_host}/{owner}/{repo}/commit/{sha}",
                    "files_changed": stats.get("total", 0),
                    "additions": stats.get("additions", 0),
                    "deletions": stats.get("deletions", 0),
                })

            return {
                "success": True,
                "server_type": "gitea",
                "repo": f"{owner}/{repo}",
                "total": len(commits),
                "page": page,
                "per_page": per_page,
                "commits": commits,
            }

    async def _fetch_gitea_commit_detail(
        self, repo_url: str, token: str, commit_sha: str
    ) -> Dict[str, Any]:
        parsed = parse_github_url(repo_url)
        host = parsed["host"]
        owner = parsed["owner"]
        repo = parsed["repo"]
        api_base = f"{host}/api/v1/repos/{owner}/{repo}"

        headers = {"Authorization": f"token {token}", "Accept": "application/json"}
        browser_host = self._to_browser_url(host)

        async with httpx.AsyncClient(timeout=30.0) as client:
            # /git/commits/{sha} includes files and stats
            resp = await client.get(f"{api_base}/git/commits/{commit_sha}", headers=headers)
            if resp.status_code != 200:
                return {"success": False, "error": f"Gitea API error {resp.status_code}: {resp.text}"}

            commit = resp.json()
            commit_info = commit.get("commit", commit)
            author_info = commit_info.get("author", {})
            stats = commit.get("stats") or {}

            files = []
            for f in commit.get("files", []):
                files.append({
                    "filename": f.get("filename", ""),
                    "old_filename": f.get("previous_filename", ""),
                    "status": f.get("status", "modified"),
                    "additions": f.get("additions", 0),
                    "deletions": f.get("deletions", 0),
                })

            sha = commit.get("sha", commit_sha)
            message = commit_info.get("message", "")
            return {
                "success": True,
                "sha": sha,
                "short_sha": sha[:7],
                "message": message.split("\n")[0],
                "full_message": message,
                "author": author_info.get("name", ""),
                "email": author_info.get("email", ""),
                "date": author_info.get("date", ""),
                "url": f"{browser_host}/{owner}/{repo}/commit/{sha}",
                "stats": {
                    "additions": stats.get("additions", 0),
                    "deletions": stats.get("deletions", 0),
                    "total": stats.get("total", 0),
                },
                "files": files,
            }


def _parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse ISO datetime string, returning None on failure."""
    if not dt_str:
        return None
    # Strip trailing Z and try parsing
    dt_str = dt_str.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.fromisoformat(dt_str)
        except ValueError:
            continue
    return None
