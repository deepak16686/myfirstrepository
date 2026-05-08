"""
Repository Analysis Functions

Standalone functions for parsing GitLab URLs and analyzing repository structure.
"""
import re
from typing import Dict, Any, List
from urllib.parse import urlparse

import httpx

from app.config import settings


LEGACY_TAILSCALE_HOSTS = {"deepak-desktop.tailac51e7.ts.net"}


def _host_name(netloc: str) -> str:
    """Return the lowercase hostname without credentials or port."""
    parsed = urlparse(f"//{netloc}")
    return (parsed.hostname or netloc).lower()


def _configured_hostname(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def _managed_gitlab_api_base() -> str:
    return settings.gitlab_url.rstrip("/")


def _is_managed_gitlab_url(netloc: str, path: str) -> bool:
    """True when the browser URL points at this local GitLab instance."""
    host = _host_name(netloc)
    public_domain = (
        (getattr(settings, "public_base_domain", None) or "").lower()
        or _configured_hostname(getattr(settings, "public_base_url", "") or "")
    )
    configured_tailscale_host = _configured_hostname(
        getattr(settings, "tailscale_base_url", "") or ""
    )

    managed_hosts = {
        "gitlab-server",
        "localhost",
        "127.0.0.1",
        "host.docker.internal",
        configured_tailscale_host,
        *LEGACY_TAILSCALE_HOSTS,
    }
    if public_domain:
        managed_hosts.update({public_domain, f"gitlab.{public_domain}"})

    if host in managed_hosts:
        return True

    # Tailscale path-router URLs expose GitLab under /gitlab. Treat those as
    # this managed instance even if the exact tailnet hostname changes later.
    return host.endswith(".ts.net") and path.startswith("gitlab/")


def parse_gitlab_url(url: str) -> Dict[str, str]:
    """
    Parse GitLab repository URL to extract project info.

    Supports:
    - https://gitlab.com/user/repo
    - https://gitlab.com/user/repo.git
    - http://localhost:8929/user/repo
    - git@gitlab.com:user/repo.git
    """
    url = url.strip().rstrip('/')

    # Handle SSH URLs
    if url.startswith('git@'):
        match = re.match(r'git@([^:]+):(.+)', url)
        if match:
            host = match.group(1)
            path = match.group(2).rstrip("/")
            if path.endswith(".git"):
                path = path[:-4]
            api_host = (
                _managed_gitlab_api_base()
                if _is_managed_gitlab_url(host, path)
                else f"https://{host}"
            )
            return {
                "host": api_host,
                "path": path,
                "project_path": path.replace('/', '%2F')
            }

    # Handle HTTP(S) URLs - preserve original protocol.
    # For GitLab instances with a relative_url_root (external_url ends in
    # "/gitlab"), the API is at `{protocol}://{host}/gitlab/api/v4/...`.
    # Detect the leading "gitlab/" path segment and promote it into the
    # host so the caller's `{host}/api/v4/...` string building works.
    match = re.match(r'(https?)://([^/]+)/(.+)', url)
    if match:
        protocol = match.group(1)
        host = match.group(2)
        path = match.group(3).rstrip("/")
        if path.endswith(".git"):
            path = path[:-4]
        had_gitlab_prefix = path.startswith("gitlab/")
        if path.startswith("gitlab/"):
            path = path[len("gitlab/"):]
        api_host = (
            _managed_gitlab_api_base()
            if _is_managed_gitlab_url(host, match.group(3).rstrip("/"))
            else f"{protocol}://{host}{'/gitlab' if had_gitlab_prefix else ''}"
        )
        return {
            "host": api_host,
            "path": path,
            "project_path": path.replace('/', '%2F')
        }

    raise ValueError(f"Invalid GitLab URL: {url}")


async def analyze_repository(repo_url: str, gitlab_token: str) -> Dict[str, Any]:
    """
    Analyze a GitLab repository to understand its structure.
    Returns information about:
    - Programming language
    - Framework
    - Existing files
    - Package manager
    """
    parsed = parse_gitlab_url(repo_url)

    async with httpx.AsyncClient() as client:
        headers = {"PRIVATE-TOKEN": gitlab_token}

        # Get project info
        project_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}"
        project_resp = await client.get(project_url, headers=headers)
        project_resp.raise_for_status()
        project = project_resp.json()

        # Get repository tree (recursive to find source files like .kt, .scala, etc.)
        tree_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/tree"
        tree_resp = await client.get(
            tree_url, headers=headers,
            params={"per_page": 100, "recursive": "true"}
        )
        files = tree_resp.json() if tree_resp.status_code == 200 else []

        # Collect all file paths for language detection (includes src/main/kotlin/*.kt etc.)
        all_file_paths = [f['path'] for f in files if f['type'] == 'blob']
        # Root-level file names for framework/package manager detection
        file_names = [f['name'] for f in files if f['type'] == 'blob' and '/' not in f['path']]

        analysis = {
            "project_id": project['id'],
            "project_name": project['name'],
            "default_branch": project.get('default_branch', 'main'),
            "files": file_names,
            "all_files": all_file_paths,
            "language": _detect_language(file_names, all_file_paths),
            "framework": _detect_framework(file_names),
            "package_manager": _detect_package_manager(file_names),
            "has_dockerfile": 'Dockerfile' in file_names,
            "has_gitlab_ci": '.gitlab-ci.yml' in file_names
        }

        return analysis


def _detect_language(files: List[str], all_paths: List[str] = None) -> str:
    """Detect primary programming language.

    Args:
        files: Root-level file names (e.g., ['pom.xml', 'README.md'])
        all_paths: All file paths including subdirectories (e.g., ['src/main/kotlin/App.kt'])
                   Used to detect languages whose source files aren't at root level.
    """
    all_files = all_paths or files

    if 'package.json' in files:
        return 'javascript'
    elif 'requirements.txt' in files or 'setup.py' in files or 'pyproject.toml' in files:
        return 'python'
    # Kotlin check BEFORE Java — Kotlin projects also use build.gradle.kts
    # Check for .kt source files (NOT .kts which could be Gradle build scripts)
    elif any(f.endswith('.kt') for f in all_files):
        return 'kotlin'
    elif 'pom.xml' in files or 'build.gradle' in files or 'build.gradle.kts' in files:
        return 'java'
    elif 'build.sbt' in files:
        return 'scala'
    elif 'go.mod' in files:
        return 'go'
    elif 'Cargo.toml' in files:
        return 'rust'
    elif 'Gemfile' in files:
        return 'ruby'
    elif 'composer.json' in files:
        return 'php'
    elif 'mix.exs' in files:
        return 'elixir'
    elif any(f.endswith('.csproj') for f in all_files) or any(f.endswith('.sln') for f in all_files):
        return 'csharp'
    elif any(f.endswith('.swift') for f in all_files) or 'Package.swift' in files:
        return 'swift'
    elif any(f.endswith('.ts') for f in all_files) and 'package.json' not in files:
        return 'typescript'
    # Perl: detect by Makefile.PL, cpanfile, dist.ini, or any .pl/.pm files
    elif (
        'Makefile.PL' in files
        or 'cpanfile' in files
        or 'dist.ini' in files
        or any(f.endswith('.pl') for f in all_files)
        or any(f.endswith('.pm') for f in all_files)
    ):
        return 'perl'
    return 'unknown'


def _detect_framework(files: List[str]) -> str:
    """Detect framework based on files"""
    if 'Makefile.PL' in files:
        return 'makefile-pl'
    elif 'cpanfile' in files:
        return 'cpanfile'
    elif 'dist.ini' in files:
        return 'dist-zilla'
    elif 'next.config.js' in files or 'next.config.mjs' in files:
        return 'nextjs'
    elif 'angular.json' in files:
        return 'angular'
    elif 'vue.config.js' in files or 'vite.config.js' in files:
        return 'vue'
    elif 'manage.py' in files:
        return 'django'
    elif 'app.py' in files or 'main.py' in files:
        if 'requirements.txt' in files:
            return 'flask-or-fastapi'
    elif 'pom.xml' in files:
        return 'spring'
    elif ('build.gradle.kts' in files or 'build.gradle' in files) and 'pom.xml' not in files:
        return 'gradle'
    elif 'build.sbt' in files:
        return 'akka'
    elif 'mix.exs' in files:
        return 'phoenix'
    elif 'artisan' in files or 'composer.json' in files:
        return 'laravel'
    return 'generic'


def _detect_package_manager(files: List[str]) -> str:
    """Detect package manager"""
    if 'cpanfile' in files:
        return 'cpanfile'
    elif 'Makefile.PL' in files:
        return 'makefile-pl'
    elif 'yarn.lock' in files:
        return 'yarn'
    elif 'package-lock.json' in files:
        return 'npm'
    elif 'pnpm-lock.yaml' in files:
        return 'pnpm'
    elif 'Pipfile.lock' in files:
        return 'pipenv'
    elif 'poetry.lock' in files:
        return 'poetry'
    elif 'requirements.txt' in files:
        return 'pip'
    return 'unknown'
