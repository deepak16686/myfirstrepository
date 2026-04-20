"""
File: analyzer.py
Purpose: Analyzes Gitea-hosted repositories to detect language, framework, and package manager,
    then enriches the result with Jenkins-specific fields (has_jenkinsfile, has_dockerfile).
    Delegates core analysis to the GitHub pipeline analyzer since both use Gitea APIs.
When Used: Called at the start of every pipeline generation request to determine what kind of
    project the repository contains, which drives template selection, image choices, and
    compile commands for the generated Jenkinsfile.
Why Created: Separated from the generator to isolate repository inspection logic and allow
    reuse of the Gitea-compatible analyzer from the github_pipeline package, avoiding code
    duplication while adding Jenkins-specific detection (Jenkinsfile/Dockerfile presence).
"""
from typing import Dict, Any, List

from app.config import settings


def parse_repo_url(url: str) -> Dict[str, str]:
    """
    Parse repository URL to extract project info.
    Works with Gitea URLs (http://gitea-server:3000/owner/repo).
    Returns: {"host", "owner", "repo"}
    """
    from app.services.github_pipeline.analyzer import parse_github_url
    return parse_github_url(url)


async def analyze_repository(repo_url: str, git_token: str) -> Dict[str, Any]:
    """
    Analyze a Gitea repository to understand its structure.
    Delegates to the github_pipeline analyzer (which speaks Gitea API).
    Adds Jenkins-specific fields.
    """
    from app.services.github_pipeline.analyzer import analyze_repository as gitea_analyze
    analysis = await gitea_analyze(repo_url, git_token)

    # Add Jenkins-specific fields
    file_names = analysis.get('files', [])
    analysis['has_jenkinsfile'] = 'Jenkinsfile' in file_names
    analysis['has_dockerfile'] = 'Dockerfile' in file_names

    return analysis


def _detect_language(files: List[str]) -> str:
    from app.services.github_pipeline.analyzer import _detect_language
    return _detect_language(files)


def _detect_framework(files: List[str]) -> str:
    from app.services.github_pipeline.analyzer import _detect_framework
    return _detect_framework(files)


def _detect_package_manager(files: List[str]) -> str:
    from app.services.github_pipeline.analyzer import _detect_package_manager
    return _detect_package_manager(files)
