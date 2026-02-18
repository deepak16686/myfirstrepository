"""
File: workspace.py
Purpose: Manages isolated temporary workspace directories for Terraform operations, writing .tf files to disk and providing CRUD operations for workspace lifecycle (create, read, update, cleanup) with automatic age-based cleanup.
When Used: Called by the LLM fixer and router when terraform CLI operations (init, validate, plan, apply) need a physical directory with .tf files on disk.
Why Created: Terraform CLI requires files on the filesystem rather than in-memory strings, so this module bridges the gap by managing temp directories with unique IDs, enabling concurrent terraform operations without conflicts.
"""
import os
import shutil
import uuid
from typing import Dict, Optional
from datetime import datetime, timedelta


class WorkspaceManager:
    """Manages terraform workspaces (temp directories with .tf files)."""

    def __init__(self, base_dir: str = "/tmp/terraform-workspaces"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self._workspaces: Dict[str, dict] = {}

    def create(self, provider: str, resource_type: str, files: Dict[str, str]) -> str:
        """Create workspace dir, write .tf files, return workspace_id."""
        workspace_id = f"tf-{provider}-{resource_type}-{uuid.uuid4().hex[:8]}"
        workspace_path = os.path.join(self.base_dir, workspace_id)
        os.makedirs(workspace_path, exist_ok=True)

        for filename, content in files.items():
            filepath = os.path.join(workspace_path, filename)
            with open(filepath, "w") as f:
                f.write(content)

        self._workspaces[workspace_id] = {
            "path": workspace_path,
            "provider": provider,
            "resource_type": resource_type,
            "created_at": datetime.now(),
            "files": list(files.keys()),
        }
        return workspace_id

    def get_path(self, workspace_id: str) -> Optional[str]:
        """Get filesystem path for a workspace."""
        info = self._workspaces.get(workspace_id)
        if info:
            return info["path"]
        # Also check if directory exists on disk
        path = os.path.join(self.base_dir, workspace_id)
        if os.path.isdir(path):
            return path
        return None

    def get_info(self, workspace_id: str) -> Optional[dict]:
        """Get workspace metadata."""
        return self._workspaces.get(workspace_id)

    def update_files(self, workspace_id: str, files: Dict[str, str]):
        """Update .tf files in an existing workspace."""
        path = self.get_path(workspace_id)
        if not path:
            raise ValueError(f"Workspace {workspace_id} not found")

        for filename, content in files.items():
            filepath = os.path.join(path, filename)
            with open(filepath, "w") as f:
                f.write(content)

        if workspace_id in self._workspaces:
            self._workspaces[workspace_id]["files"] = list(
                set(self._workspaces[workspace_id].get("files", []) + list(files.keys()))
            )

    def read_files(self, workspace_id: str) -> Dict[str, str]:
        """Read all .tf files from a workspace."""
        path = self.get_path(workspace_id)
        if not path:
            return {}

        files = {}
        for filename in os.listdir(path):
            if filename.endswith(".tf") or filename == "terraform.tfvars":
                filepath = os.path.join(path, filename)
                with open(filepath, "r") as f:
                    files[filename] = f.read()
        return files

    def cleanup(self, workspace_id: str):
        """Remove workspace directory."""
        path = self.get_path(workspace_id)
        if path and os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
        self._workspaces.pop(workspace_id, None)

    def cleanup_old(self, max_age_hours: int = 24):
        """Cleanup workspaces older than max_age_hours."""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        to_remove = []
        for wid, info in self._workspaces.items():
            if info.get("created_at", datetime.now()) < cutoff:
                to_remove.append(wid)

        for wid in to_remove:
            self.cleanup(wid)


# Singleton instance
workspace_manager = WorkspaceManager()
