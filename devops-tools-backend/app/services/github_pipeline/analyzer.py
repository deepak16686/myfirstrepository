"""
Repository analysis functions for GitHub/Gitea repositories.

Provides URL parsing, language/framework/package-manager detection.
"""
import re
import httpx
from typing import Dict, Any, List

from app.config import settings


def parse_github_url(url: str) -> Dict[str, str]:
    """Parse GitHub/Gitea repository URL to extract owner and repo"""
    url = url.rstrip('/').replace('.git', '')

    # Handle SSH URLs (git@github.com:owner/repo)
    if url.startswith('git@'):
        match = re.match(r'git@([^:]+):(.+)/(.+)', url)
        if match:
            return {
                "host": f"https://{match.group(1)}",
                "owner": match.group(2),
                "repo": match.group(3)
            }

    # Handle HTTP(S) URLs
    match = re.match(r'(https?)://([^/]+)/([^/]+)/([^/]+)', url)
    if match:
        return {
            "host": f"{match.group(1)}://{match.group(2)}",
            "owner": match.group(3),
            "repo": match.group(4)
        }

    raise ValueError(f"Invalid GitHub/Gitea URL: {url}")


async def analyze_repository(
    repo_url: str,
    github_token: str
) -> Dict[str, Any]:
    """Analyze repository to detect language, framework, and structure"""
    parsed = parse_github_url(repo_url)
    owner = parsed["owner"]
    repo = parsed["repo"]
    host = parsed["host"]

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }

        # Get repository info
        repo_response = await client.get(
            f"{host}/api/v1/repos/{owner}/{repo}" if "gitea" in host.lower() or host == settings.github_url
            else f"{host}/repos/{owner}/{repo}",
            headers=headers
        )
        repo_info = repo_response.json() if repo_response.status_code == 200 else {}

        # Get file tree
        default_branch = repo_info.get("default_branch", "main")

        # Try to get contents
        contents_response = await client.get(
            f"{host}/api/v1/repos/{owner}/{repo}/contents" if "gitea" in host.lower() or host == settings.github_url
            else f"{host}/repos/{owner}/{repo}/contents",
            headers=headers,
            params={"ref": default_branch}
        )

        files = []
        if contents_response.status_code == 200:
            contents = contents_response.json()
            if isinstance(contents, list):
                files = [f.get("name", f.get("path", "")) for f in contents]

    # Detect language
    language = _detect_language(files)
    framework = _detect_framework(files)
    package_manager = _detect_package_manager(files)

    return {
        "owner": owner,
        "repo": repo,
        "default_branch": default_branch,
        "files": files,
        "language": language,
        "framework": framework,
        "package_manager": package_manager,
        "has_dockerfile": "Dockerfile" in files or "dockerfile" in [f.lower() for f in files],
        "has_workflow": ".github" in files or any("workflow" in f.lower() for f in files)
    }


def _detect_language(files: List[str]) -> str:
    """Detect primary programming language"""
    file_set = set(f.lower() for f in files)

    if "pom.xml" in file_set or "build.gradle" in file_set:
        return "java"
    if "package.json" in file_set:
        return "javascript"
    if "requirements.txt" in file_set or "setup.py" in file_set or "pyproject.toml" in file_set:
        return "python"
    if "go.mod" in file_set:
        return "go"
    if "cargo.toml" in file_set:
        return "rust"
    if "gemfile" in file_set:
        return "ruby"
    if any(f.endswith(".csproj") for f in files):
        return "csharp"

    return "unknown"


def _detect_framework(files: List[str]) -> str:
    """Detect framework"""
    file_set = set(f.lower() for f in files)

    if "next.config.js" in file_set or "next.config.mjs" in file_set:
        return "nextjs"
    if "angular.json" in file_set:
        return "angular"
    if "vue.config.js" in file_set:
        return "vue"
    if "manage.py" in file_set:
        return "django"
    if "app.py" in file_set or "main.py" in file_set:
        return "flask"
    if "pom.xml" in file_set:
        return "spring"

    return "generic"


def _detect_package_manager(files: List[str]) -> str:
    """Detect package manager"""
    file_set = set(f.lower() for f in files)

    if "yarn.lock" in file_set:
        return "yarn"
    if "package-lock.json" in file_set:
        return "npm"
    if "pnpm-lock.yaml" in file_set:
        return "pnpm"
    if "poetry.lock" in file_set:
        return "poetry"
    if "pipfile.lock" in file_set:
        return "pipenv"
    if "requirements.txt" in file_set:
        return "pip"
    if "build.gradle" in file_set:
        return "gradle"
    if "pom.xml" in file_set:
        return "maven"

    return "unknown"
