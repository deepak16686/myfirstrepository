"""
File: analyzer.py
Purpose: Analyzes GitHub/Gitea repositories to detect programming language, framework, package
    manager, and project structure by fetching the file tree and key config files via the Gitea API.
When Used: Called at the start of every pipeline generation flow (generate_workflow_files,
    generate_with_validation, self-healing workflow) to produce the analysis dict that drives
    template selection, LLM prompting, and image seeding.
Why Created: Extracted from the monolithic pipeline_generator.py to isolate repository analysis
    logic (URL parsing, language detection, deep file content scanning) into a single focused module.
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

    is_gitea = "gitea" in host.lower() or host == settings.github_url

    async with httpx.AsyncClient(timeout=30.0) as client:
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json"
        }

        # Get repository info
        repo_response = await client.get(
            f"{host}/api/v1/repos/{owner}/{repo}" if is_gitea
            else f"{host}/repos/{owner}/{repo}",
            headers=headers
        )
        repo_info = repo_response.json() if repo_response.status_code == 200 else {}

        # Get file tree
        default_branch = repo_info.get("default_branch", "main")

        # Try to get root-level contents
        contents_response = await client.get(
            f"{host}/api/v1/repos/{owner}/{repo}/contents" if is_gitea
            else f"{host}/repos/{owner}/{repo}/contents",
            headers=headers,
            params={"ref": default_branch}
        )

        files = []
        if contents_response.status_code == 200:
            contents = contents_response.json()
            if isinstance(contents, list):
                files = [f.get("name", f.get("path", "")) for f in contents]

        # Fetch recursive tree for deeper language detection (e.g., .kt files in src/)
        all_paths = list(files)  # Start with root files as fallback
        if is_gitea:
            try:
                tree_response = await client.get(
                    f"{host}/api/v1/repos/{owner}/{repo}/git/trees/{default_branch}",
                    headers=headers,
                    params={"recursive": "true"}
                )
                if tree_response.status_code == 200:
                    tree_data = tree_response.json()
                    all_paths = [
                        e["path"] for e in tree_data.get("tree", [])
                        if e.get("type") == "blob"
                    ]
            except Exception:
                pass  # Fall back to root-level files

        # Detect language (with recursive paths for Kotlin/.kt etc.)
        language = _detect_language(files, all_paths)
        framework = _detect_framework(files)
        package_manager = _detect_package_manager(files)

        analysis = {
            "owner": owner,
            "repo": repo,
            "default_branch": default_branch,
            "files": files,
            "all_paths": all_paths,
            "language": language,
            "framework": framework,
            "package_manager": package_manager,
            "has_dockerfile": "Dockerfile" in files or "dockerfile" in [f.lower() for f in files],
            "has_workflow": ".github" in files or any("workflow" in f.lower() for f in files)
        }

        # Deep content analysis — reads key config files for richer detection
        from app.services.shared.deep_analyzer import deep_analyze

        async def _read_gitea_file(path: str):
            try:
                r = await client.get(
                    f"{host}/api/v1/repos/{owner}/{repo}/raw/{path}",
                    headers=headers,
                    params={"ref": default_branch}
                )
                return r.text if r.status_code == 200 else None
            except Exception:
                return None

        deep = await deep_analyze(
            language, framework,
            files, all_paths, _read_gitea_file
        )
        analysis.update(deep)

        # Override framework if deep analysis found a more specific one
        if deep.get("framework"):
            analysis["framework"] = deep["framework"]

        # Resolve dynamic images and pre-seed into Nexus
        from app.services.shared.deep_analyzer import resolve_and_seed_images
        await resolve_and_seed_images(analysis)

        return analysis


def _detect_language(files: List[str], all_paths: List[str] = None) -> str:
    """Detect primary programming language.

    Args:
        files: Root-level file names.
        all_paths: All file paths including subdirectories (for .kt, .scala, etc.).
    """
    file_set = set(f.lower() for f in files)
    all_files = all_paths or files

    if "package.json" in file_set:
        return "javascript"
    if "requirements.txt" in file_set or "setup.py" in file_set or "pyproject.toml" in file_set:
        return "python"
    # Kotlin check BEFORE Java — Kotlin projects also use build.gradle.kts
    if any(f.endswith(".kt") for f in all_files):
        return "kotlin"
    if "pom.xml" in file_set or "build.gradle" in file_set or "build.gradle.kts" in file_set:
        return "java"
    if "build.sbt" in file_set:
        return "scala"
    if "go.mod" in file_set:
        return "go"
    if "cargo.toml" in file_set:
        return "rust"
    if "gemfile" in file_set:
        return "ruby"
    if "composer.json" in file_set:
        return "php"
    if "mix.exs" in file_set:
        return "elixir"
    if any(f.endswith(".csproj") for f in all_files) or any(f.endswith(".sln") for f in all_files):
        return "csharp"
    if any(f.endswith(".ts") for f in all_files) and "package.json" not in file_set:
        return "typescript"

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
