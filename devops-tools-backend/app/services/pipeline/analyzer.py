"""
Repository Analysis Functions

Standalone functions for parsing GitLab URLs and analyzing repository structure.
"""
import re
from typing import Dict, Any, List

import httpx

from app.config import settings


def parse_gitlab_url(url: str) -> Dict[str, str]:
    """
    Parse GitLab repository URL to extract project info.

    Supports:
    - https://gitlab.com/user/repo
    - https://gitlab.com/user/repo.git
    - http://localhost:8929/user/repo
    - git@gitlab.com:user/repo.git
    """
    # Remove .git suffix if present
    url = url.rstrip('/').replace('.git', '')

    # Handle SSH URLs
    if url.startswith('git@'):
        match = re.match(r'git@([^:]+):(.+)', url)
        if match:
            host = match.group(1)
            path = match.group(2)
            return {
                "host": f"https://{host}",
                "path": path,
                "project_path": path.replace('/', '%2F')
            }

    # Handle HTTP(S) URLs - preserve original protocol
    match = re.match(r'(https?)://([^/]+)/(.+)', url)
    if match:
        protocol = match.group(1)
        host = match.group(2)
        path = match.group(3)
        return {
            "host": f"{protocol}://{host}",
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

        # Get repository tree (root level files)
        tree_url = f"{parsed['host']}/api/v4/projects/{parsed['project_path']}/repository/tree"
        tree_resp = await client.get(tree_url, headers=headers, params={"per_page": 100})
        files = tree_resp.json() if tree_resp.status_code == 200 else []

        # Detect language and framework based on files
        file_names = [f['name'] for f in files if f['type'] == 'blob']

        analysis = {
            "project_id": project['id'],
            "project_name": project['name'],
            "default_branch": project.get('default_branch', 'main'),
            "files": file_names,
            "language": _detect_language(file_names),
            "framework": _detect_framework(file_names),
            "package_manager": _detect_package_manager(file_names),
            "has_dockerfile": 'Dockerfile' in file_names,
            "has_gitlab_ci": '.gitlab-ci.yml' in file_names
        }

        return analysis


def _detect_language(files: List[str]) -> str:
    """Detect primary programming language"""
    if 'package.json' in files:
        return 'javascript'
    elif 'requirements.txt' in files or 'setup.py' in files or 'pyproject.toml' in files:
        return 'python'
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
    elif any(f.endswith('.csproj') for f in files) or any(f.endswith('.sln') for f in files):
        return 'csharp'
    elif any(f.endswith('.kt') for f in files) or any(f.endswith('.kts') for f in files):
        return 'kotlin'
    elif any(f.endswith('.swift') for f in files) or 'Package.swift' in files:
        return 'swift'
    elif any(f.endswith('.ts') for f in files) and 'package.json' not in files:
        return 'typescript'
    return 'unknown'


def _detect_framework(files: List[str]) -> str:
    """Detect framework based on files"""
    if 'next.config.js' in files or 'next.config.mjs' in files:
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
    elif 'build.sbt' in files:
        return 'akka'
    elif 'mix.exs' in files:
        return 'phoenix'
    elif 'artisan' in files or 'composer.json' in files:
        return 'laravel'
    return 'generic'


def _detect_package_manager(files: List[str]) -> str:
    """Detect package manager"""
    if 'yarn.lock' in files:
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
