"""
File: __init__.py
Purpose: Package initializer for the Commit History service. Exposes the CommitHistoryService class and a singleton instance for fetching git commit history from GitLab and Gitea repositories.
When Used: Imported by the commit history router and by the release notes service which needs commit data to generate changelogs.
Why Created: Follows the singleton package pattern, providing a single import path for commit history retrieval that abstracts away the differences between GitLab and Gitea APIs.
"""
from app.services.commit_history.service import CommitHistoryService

commit_history_service = CommitHistoryService()

__all__ = ["CommitHistoryService", "commit_history_service"]
