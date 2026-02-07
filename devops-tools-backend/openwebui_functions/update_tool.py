#!/usr/bin/env python3
from sqlalchemy import create_engine, text
import time

engine = create_engine("sqlite:////app/backend/data/webui.db")

tool_id = "gitlab_pipeline_generator"
now = int(time.time())

content = '''"""
title: GitLab Pipeline Generator
author: AI DevOps Platform
version: 1.0.0
"""

import httpx
from pydantic import BaseModel, Field

class Tools:
    class Valves(BaseModel):
        BACKEND_URL: str = Field(
            default="http://devops-tools-backend:8003",
            description="DevOps Tools Backend URL"
        )
        GITLAB_TOKEN: str = Field(
            default="glpat-gZVCeqtC6C9FmDjqZ87CdW86MQp1OjEH.01.0w1fzferv",
            description="GitLab API Token"
        )

    def __init__(self):
        self.valves = self.Valves()

    async def generate_pipeline(self, repo_url: str, __user__: dict = {}) -> str:
        """
        Generate CI/CD pipeline for a GitLab repository.
        :param repo_url: GitLab repository URL
        :return: Generated files for approval
        """
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/generate",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "model": "pipeline-generator-v5"
                    }
                )
                result = response.json()
                if result.get("success"):
                    analysis = result.get("analysis", {})
                    return f"""## Pipeline Generated!

**Language:** {analysis.get("language", "Unknown")}
**Framework:** {analysis.get("framework", "Unknown")}

### Dockerfile
```dockerfile
{result["dockerfile"]}
```

### .gitlab-ci.yml
```yaml
{result["gitlab_ci"]}
```

---
**Approve?** Reply **yes** to commit."""
                return f"Error: {result}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def approve_and_commit(self, repo_url: str, __user__: dict = {}) -> str:
        """
        Commit pipeline files to GitLab after approval.
        :param repo_url: GitLab repository URL
        :return: Commit result
        """
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                # Generate
                gen = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/generate",
                    json={"repo_url": repo_url, "gitlab_token": self.valves.GITLAB_TOKEN, "model": "pipeline-generator-v5"}
                )
                gen_result = gen.json()
                if not gen_result.get("success"):
                    return f"Error: {gen_result}"

                # Commit
                commit = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/commit",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "gitlab_ci": gen_result["gitlab_ci"],
                        "dockerfile": gen_result["dockerfile"]
                    }
                )
                result = commit.json()
                if result.get("success"):
                    return f"""## Committed!
**Branch:** `{result["branch"]}`
**Commit:** `{result["commit_id"]}`
Pipeline triggered!"""
                return f"Error: {result}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def check_pipeline_status(self, repo_url: str, branch: str, __user__: dict = {}) -> str:
        """
        Check pipeline status.
        :param repo_url: GitLab repository URL
        :param branch: Branch name
        :return: Status
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/status",
                    json={"repo_url": repo_url, "gitlab_token": self.valves.GITLAB_TOKEN, "branch": branch}
                )
                result = response.json()
                status = result.get("status", "unknown")
                return f"Pipeline: {status.upper()} (ID: {result.get('pipeline_id', 'N/A')})"
        except Exception as e:
            return f"Error: {str(e)}"
'''

with engine.connect() as conn:
    conn.execute(text("UPDATE tool SET content = :content, updated_at = :updated_at WHERE id = :id"),
        {"content": content, "updated_at": now, "id": tool_id})
    conn.commit()
    print("Tool updated successfully!")
