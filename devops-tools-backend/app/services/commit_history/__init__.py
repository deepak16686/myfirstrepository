"""Commit History Service Package."""
from app.services.commit_history.service import CommitHistoryService

commit_history_service = CommitHistoryService()

__all__ = ["CommitHistoryService", "commit_history_service"]
