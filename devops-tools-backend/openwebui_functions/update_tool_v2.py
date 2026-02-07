#!/usr/bin/env python3
from sqlalchemy import create_engine, text
import time

engine = create_engine("sqlite:////app/backend/data/webui.db")

tool_id = "gitlab_pipeline_generator"
now = int(time.time())

content = '''"""
title: GitLab Pipeline Generator
author: AI DevOps Platform
version: 2.0.0
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
        self._last_repo = None

    async def generate_pipeline(self, repo_url: str, __user__: dict = {}) -> str:
        """
        Generate CI/CD pipeline for a GitLab repository. Call this when user provides a repo URL.
        :param repo_url: GitLab repository URL (e.g., http://gitlab-server/root/java-app.git)
        :return: Generated Dockerfile and .gitlab-ci.yml for user approval
        """
        self._last_repo = repo_url
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/api/v1/pipeline/generate",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "model": "pipeline-generator-v5"
                    }
                )

                if response.status_code != 200:
                    return f"API Error: {response.status_code} - {response.text}"

                result = response.json()

                if result.get("success"):
                    analysis = result.get("analysis", {})
                    return f"""## Pipeline Generated Successfully!

**Repository:** {repo_url}
**Language:** {analysis.get("language", "Unknown")}
**Framework:** {analysis.get("framework", "Unknown")}

---

### Dockerfile
```dockerfile
{result["dockerfile"]}
```

---

### .gitlab-ci.yml
```yaml
{result["gitlab_ci"]}
```

---

## Action Required

**Do you approve committing these files to the repository?**

Reply **"yes"** to commit these files, or **"no"** to cancel.
"""
                else:
                    return f"Error generating pipeline: {result.get('detail', str(result))}"
        except Exception as e:
            return f"Error connecting to backend: {str(e)}"

    async def approve_and_commit(self, repo_url: str, __user__: dict = {}) -> str:
        """
        Commit the generated pipeline files to GitLab. Call this when user approves (says yes).
        :param repo_url: GitLab repository URL to commit to
        :return: Commit result with branch name and pipeline info
        """
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                # First regenerate the files
                gen_response = await client.post(
                    f"{self.valves.BACKEND_URL}/api/v1/pipeline/generate",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "model": "pipeline-generator-v5"
                    }
                )

                if gen_response.status_code != 200:
                    return f"Generate Error: {gen_response.status_code}"

                gen_result = gen_response.json()

                if not gen_result.get("success"):
                    return f"Error generating: {gen_result.get('detail', str(gen_result))}"

                # Now commit the files
                commit_response = await client.post(
                    f"{self.valves.BACKEND_URL}/api/v1/pipeline/commit",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "gitlab_ci": gen_result["gitlab_ci"],
                        "dockerfile": gen_result["dockerfile"],
                        "commit_message": "Add CI/CD pipeline configuration [AI Generated]"
                    }
                )

                if commit_response.status_code != 200:
                    return f"Commit Error: {commit_response.status_code} - {commit_response.text}"

                result = commit_response.json()

                if result.get("success"):
                    return f"""## Files Committed Successfully!

**Branch:** `{result["branch"]}`
**Commit ID:** `{result["commit_id"]}`
**Project ID:** {result.get("project_id", "N/A")}

🚀 **Pipeline has been triggered!**

The GitLab CI/CD pipeline is now running automatically.

You can check the pipeline status in GitLab or ask me to check it.
"""
                else:
                    return f"Error committing: {result.get('detail', str(result))}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def check_pipeline_status(self, repo_url: str, branch: str, __user__: dict = {}) -> str:
        """
        Check the status of a GitLab CI/CD pipeline.
        :param repo_url: GitLab repository URL
        :param branch: Branch name to check
        :return: Pipeline status and job details
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/api/v1/pipeline/status",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "branch": branch
                    }
                )

                result = response.json()

                if result.get("success"):
                    status = result.get("status", "unknown")
                    emoji = {
                        "success": "✅",
                        "failed": "❌",
                        "running": "🔄",
                        "pending": "⏳",
                        "canceled": "🚫"
                    }.get(status, "❓")

                    output = f"""## Pipeline Status: {emoji} {status.upper()}

**Pipeline ID:** {result.get("pipeline_id", "N/A")}
**Duration:** {result.get("duration", "N/A")} seconds
**Web URL:** {result.get("web_url", "N/A")}
"""
                    if result.get("failed_jobs"):
                        output += "\\n### Failed Jobs:\\n"
                        for job in result["failed_jobs"]:
                            output += f"- **{job['name']}** (stage: {job['stage']})\\n"

                    return output
                else:
                    return f"Status: {result.get('message', 'No pipeline found')}"
        except Exception as e:
            return f"Error: {str(e)}"
'''

with engine.connect() as conn:
    conn.execute(text("UPDATE tool SET content = :content, updated_at = :updated_at WHERE id = :id"),
        {"content": content, "updated_at": now, "id": tool_id})
    conn.commit()
    print("Tool updated with correct API paths!")
