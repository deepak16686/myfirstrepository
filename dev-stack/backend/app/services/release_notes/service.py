"""
Release Notes Generator Service

Fetches commits from a repo and generates formatted release notes via LLM.
"""
from typing import Dict, Any, Optional

from app.services.commit_history import commit_history_service
from app.integrations.llm_provider import get_llm_provider


RELEASE_NOTES_SYSTEM_PROMPT = """You are a release notes generator. Given a list of git commits, generate well-formatted markdown release notes.

Rules:
- Group commits by type: Features, Bug Fixes, Improvements, Refactoring, Documentation, Other
- Infer the type from commit message prefixes (feat:, fix:, chore:, docs:, refactor:, test:, ci:, etc.)
- If no prefix, analyze the message content to categorize appropriately
- Write a brief 1-2 sentence summary at the top describing the overall changes
- Use bullet points for individual changes
- Omit merge commits and trivial commits (like "initial commit")
- Keep descriptions concise but informative
- Include the short SHA in parentheses after each item
- Format as valid Markdown
"""

KEEPACHANGELOG_SYSTEM_PROMPT = """You are a release notes generator following the Keep a Changelog format (https://keepachangelog.com).

Given a list of git commits, generate markdown release notes with these sections:
### Added - for new features
### Changed - for changes in existing functionality
### Deprecated - for soon-to-be removed features
### Removed - for now removed features
### Fixed - for any bug fixes
### Security - for vulnerability fixes

Rules:
- Only include sections that have entries
- Infer the category from commit messages
- Include the short SHA in parentheses after each item
- Format as valid Markdown
"""

DETAILED_SYSTEM_PROMPT = """You are a release notes generator producing detailed changelogs.

Given a list of git commits, generate detailed markdown release notes:
- Group by category (Features, Fixes, Improvements, etc.)
- For each entry include: description, author, short SHA
- Include a statistics section at the end: total commits, contributors, date range
- Format as valid Markdown
"""


class ReleaseNotesService:
    """Service for generating release notes from git commits via LLM."""

    async def generate_release_notes(
        self,
        repo_url: str,
        token: Optional[str] = None,
        since: str = "",
        until: str = "",
        branch: Optional[str] = None,
        format_style: str = "standard",
    ) -> Dict[str, Any]:
        """Fetch commits and generate release notes."""
        # 1. Fetch commits
        commit_result = await commit_history_service.get_commits(
            repo_url=repo_url,
            token=token,
            since=since,
            until=until,
            branch=branch,
            page=1,
            per_page=200,
        )

        if not commit_result.get("success"):
            return {"success": False, "error": commit_result.get("error", "Failed to fetch commits")}

        commits = commit_result.get("commits", [])
        if not commits:
            return {
                "success": True,
                "release_notes": "No commits found in the specified range.",
                "commit_count": 0,
                "repo": commit_result.get("repo"),
                "branch": branch,
                "date_range": {"since": since, "until": until},
                "format_style": format_style,
            }

        # 2. Build prompt from commits
        repo_name = commit_result.get("repo", repo_url)
        commit_lines = []
        for c in commits:
            sha = c.get("sha", "")[:7]
            author = c.get("author", "unknown")
            date = c.get("date", "")
            message = c.get("message", "").strip().split("\n")[0]  # first line only
            commit_lines.append(f"- {sha} | {author} | {date} | {message}")

        prompt = f"""Repository: {repo_name}
Branch: {branch or 'default'}
Date range: {since} to {until}
Total commits: {len(commits)}

Commits:
{chr(10).join(commit_lines)}

Generate release notes for the above commits."""

        # 3. Select system prompt based on format style
        system_prompts = {
            "standard": RELEASE_NOTES_SYSTEM_PROMPT,
            "keepachangelog": KEEPACHANGELOG_SYSTEM_PROMPT,
            "detailed": DETAILED_SYSTEM_PROMPT,
        }
        system_prompt = system_prompts.get(format_style, RELEASE_NOTES_SYSTEM_PROMPT)

        # 4. Generate via LLM
        provider = get_llm_provider()
        try:
            result = await provider.generate(
                model=None,
                prompt=prompt,
                system=system_prompt,
                context=None,
                options={"temperature": 0.3, "num_predict": 4000},
            )
            release_notes = result.get("response", "")
        except Exception as e:
            return {"success": False, "error": f"LLM generation failed: {e}"}
        finally:
            await provider.close()

        return {
            "success": True,
            "release_notes": release_notes,
            "commit_count": len(commits),
            "repo": repo_name,
            "branch": branch,
            "date_range": {"since": since, "until": until},
            "format_style": format_style,
        }
