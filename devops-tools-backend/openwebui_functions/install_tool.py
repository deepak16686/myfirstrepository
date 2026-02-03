#!/usr/bin/env python3
"""
Script to install GitLab Pipeline Generator tool into Open WebUI
Run this inside the Open WebUI container
"""

from open_webui.internal.db import get_session
from open_webui.models.tools import Tools, ToolForm

TOOL_CONTENT = '''
"""
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
            default="glpat-0bUTWqk5zJ5MmWjD4_ctNG86MQp1OjEH.01.0w1xz49r7",
            description="GitLab API Token"
        )

    def __init__(self):
        self.valves = self.Valves()

    async def generate_pipeline(
        self,
        repo_url: str,
        __user__: dict = {}
    ) -> str:
        """
        Generate CI/CD pipeline for a GitLab repository. Use this when user provides a GitLab repo URL.

        :param repo_url: The GitLab repository URL (e.g., http://gitlab-server/root/my-project.git)
        :return: Generated Dockerfile and .gitlab-ci.yml for approval
        """
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/api/v1/pipeline/generate",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "additional_context": "",
                        "model": "llama3.1:8b"
                    }
                )
                result = response.json()

                if result.get("success"):
                    analysis = result.get("analysis", {})
                    return f"""## Pipeline Generated Successfully!

### Repository Analysis
- **Language:** {analysis.get('language', 'Unknown')}
- **Framework:** {analysis.get('framework', 'Unknown')}

---

### Dockerfile
```dockerfile
{result['dockerfile']}
```

---

### .gitlab-ci.yml
```yaml
{result['gitlab_ci']}
```

---

**Do you approve committing these files to the repository?**

Type **yes** to commit or **no** to cancel.

<!-- PIPELINE_DATA
REPO_URL={repo_url}
-->
"""
                else:
                    return f"Error generating pipeline: {result.get('detail', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def commit_pipeline(
        self,
        repo_url: str,
        __user__: dict = {}
    ) -> str:
        """
        Commit the generated pipeline files to GitLab repository. Use this when user approves (says yes).

        :param repo_url: The GitLab repository URL to commit to
        :return: Commit result with branch name
        """
        try:
            # First generate to get the files
            async with httpx.AsyncClient(timeout=180.0) as client:
                gen_response = await client.post(
                    f"{self.valves.BACKEND_URL}/api/v1/pipeline/generate",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "model": "llama3.1:8b"
                    }
                )
                gen_result = gen_response.json()

                if not gen_result.get("success"):
                    return f"Error generating: {gen_result}"

                # Now commit
                commit_response = await client.post(
                    f"{self.valves.BACKEND_URL}/api/v1/pipeline/commit",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "gitlab_ci": gen_result["gitlab_ci"],
                        "dockerfile": gen_result["dockerfile"],
                        "commit_message": "Add CI/CD pipeline [AI Generated]"
                    }
                )
                result = commit_response.json()

                if result.get("success"):
                    return f"""## Files Committed Successfully!

**Branch:** `{result['branch']}`
**Commit ID:** `{result['commit_id']}`

Pipeline has been triggered automatically!

Check pipeline status at GitLab or ask me to check the pipeline status.
"""
                else:
                    return f"Error committing: {result.get('detail', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def check_pipeline_status(
        self,
        repo_url: str,
        branch: str,
        __user__: dict = {}
    ) -> str:
        """
        Check GitLab CI/CD pipeline status.

        :param repo_url: The GitLab repository URL
        :param branch: The branch name to check
        :return: Pipeline status
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

                status = result.get("status", "unknown")
                emoji = {"success": "✅", "failed": "❌", "running": "🔄", "pending": "⏳"}.get(status, "❓")

                output = f"""## Pipeline Status: {emoji} {status.upper()}

**Pipeline ID:** {result.get('pipeline_id', 'N/A')}
**Duration:** {result.get('duration', 'N/A')} seconds
"""
                if result.get("failed_jobs"):
                    output += "\\n### Failed Jobs:\\n"
                    for job in result["failed_jobs"]:
                        output += f"- {job['name']} (stage: {job['stage']})\\n"

                return output
        except Exception as e:
            return f"Error: {str(e)}"
'''

def main():
    db = next(get_session())

    tool_id = "gitlab_pipeline_generator"

    # Check if tool exists and delete it
    existing = Tools.get_tool_by_id(db, tool_id)
    if existing:
        print(f"Tool {tool_id} already exists, deleting...")
        Tools.delete_tool_by_id(db, tool_id)

    # Create the tool
    form = ToolForm(
        id=tool_id,
        name="GitLab Pipeline Generator",
        content=TOOL_CONTENT,
        meta={
            "description": "Automatically generates and commits CI/CD pipelines to GitLab repositories"
        }
    )

    # Use the admin user ID from the logs
    user_id = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"

    tool = Tools.insert_new_tool(db, user_id, form)
    if tool:
        print(f"✅ Tool created successfully!")
        print(f"   ID: {tool.id}")
        print(f"   Name: {tool.name}")
    else:
        print("❌ Failed to create tool")

if __name__ == "__main__":
    main()
