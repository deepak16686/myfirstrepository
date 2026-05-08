"""
Pipeline Progress Store - In-memory tracking of pipeline monitoring and self-healing progress.

Keyed by "{project_id}:{branch}" so the frontend can poll by the values
it receives from the commit response.
"""
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass, field


@dataclass
class ProgressEvent:
    timestamp: str
    stage: str
    message: str
    attempt: int = 0
    max_attempts: int = 10


@dataclass
class PipelineProgress:
    project_id: int
    branch: str
    status: str = "monitoring"
    current_message: str = "Monitoring pipeline..."
    attempt: int = 0
    max_attempts: int = 10
    pipeline_id: Optional[int] = None
    events: List[ProgressEvent] = field(default_factory=list)
    completed: bool = False
    model_used: Optional[str] = None
    fixer_model_used: Optional[str] = None
    # User-facing GitLab URLs the portal renders as click-through links
    # while the pipeline is still running. Both are filled in by the
    # monitor as soon as it learns project_path / pipeline_id.
    pipelines_browser_url: Optional[str] = None  # /-/pipelines?ref=<branch>
    pipeline_web_url: Optional[str] = None       # /-/pipelines/<pipeline_id>

    def add_event(self, stage: str, message: str, attempt: int = 0):
        self.status = stage
        self.current_message = message
        self.attempt = attempt
        self.events.append(ProgressEvent(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            stage=stage,
            message=message,
            attempt=attempt,
            max_attempts=self.max_attempts
        ))

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "branch": self.branch,
            "status": self.status,
            "current_message": self.current_message,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "pipeline_id": self.pipeline_id,
            "completed": self.completed,
            "model_used": self.model_used,
            "fixer_model_used": self.fixer_model_used,
            "pipelines_browser_url": self.pipelines_browser_url,
            "pipeline_web_url": self.pipeline_web_url,
            "events": [
                {
                    "timestamp": e.timestamp,
                    "stage": e.stage,
                    "message": e.message,
                    "attempt": e.attempt,
                    "max_attempts": e.max_attempts
                }
                for e in self.events
            ]
        }


class PipelineProgressStore:

    def __init__(self):
        self._store: Dict[str, PipelineProgress] = {}

    def _key(self, project_id: int, branch: str) -> str:
        return f"{project_id}:{branch}"

    def create(self, project_id: int, branch: str, max_attempts: int = 10) -> PipelineProgress:
        key = self._key(project_id, branch)
        progress = PipelineProgress(
            project_id=project_id,
            branch=branch,
            max_attempts=max_attempts
        )
        progress.add_event("monitoring", "Pipeline committed. Waiting for pipeline to start...")
        self._store[key] = progress
        return progress

    def get(self, project_id: int, branch: str) -> Optional[PipelineProgress]:
        return self._store.get(self._key(project_id, branch))

    def update(self, project_id: int, branch: str, stage: str, message: str, attempt: int = 0):
        progress = self.get(project_id, branch)
        if progress:
            progress.add_event(stage, message, attempt)

    def complete(self, project_id: int, branch: str, stage: str, message: str):
        progress = self.get(project_id, branch)
        if progress:
            progress.add_event(stage, message)
            progress.completed = True

    def set_pipeline_id(self, project_id: int, branch: str, pipeline_id: int):
        progress = self.get(project_id, branch)
        if progress:
            progress.pipeline_id = pipeline_id

    def set_urls(
        self,
        project_id: int,
        branch: str,
        pipelines_browser_url: Optional[str] = None,
        pipeline_web_url: Optional[str] = None,
    ):
        """Attach click-through URLs the portal can render as live links."""
        progress = self.get(project_id, branch)
        if not progress:
            return
        if pipelines_browser_url:
            progress.pipelines_browser_url = pipelines_browser_url
        if pipeline_web_url:
            progress.pipeline_web_url = pipeline_web_url


# Singleton instance
progress_store = PipelineProgressStore()
