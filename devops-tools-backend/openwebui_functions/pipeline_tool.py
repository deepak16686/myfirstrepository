"""
title: GitLab Pipeline Generator
author: AI DevOps Platform
version: 1.0.0
description: Generates and commits CI/CD pipelines to GitLab repositories
"""

import httpx
from pydantic import BaseModel, Field
from typing import Optional


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

    async def generate_and_show_pipeline(
        self,
        repo_url: str,
        __user__: dict = {}
    ) -> str:
        """
        Analyze repository and generate CI/CD pipeline files. Call this when user provides a GitLab repo URL.

        :param repo_url: The GitLab repository URL (e.g., http://gitlab-server/root/java-new-pipeline-test.git)
        :return: Generated Dockerfile and .gitlab-ci.yml for user approval
        """
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                # Call backend to generate pipeline
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/generate",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "additional_context": "",
                        "model": "pipeline-generator-v4"
                    }
                )

                if response.status_code != 200:
                    return f"Error: Backend returned status {response.status_code}"

                # FIX: Handle None response
                result = response.json() or {}

                if result.get("success"):
                    # Store generated files for later commit
                    return f"""## ✅ Pipeline Generated Successfully!

### Repository Analysis
- **Project:** {result['analysis'].get('project_name', 'Unknown')}
- **Language:** {result['analysis'].get('language', 'Unknown')}
- **Framework:** {result['analysis'].get('framework', 'Unknown')}

---

### Generated Dockerfile
```dockerfile
{result['dockerfile']}
```

---

### Generated .gitlab-ci.yml
```yaml
{result['gitlab_ci']}
```

---

## 🔔 Action Required

**Do you approve committing these files to `{repo_url}`?**

Reply **"yes"** or **"approve"** to commit these files to the repository.
Reply **"no"** to cancel.

---
_GENERATED_FILES_DATA_START_
REPO_URL={repo_url}
DOCKERFILE_START
{result['dockerfile']}
DOCKERFILE_END
GITLABCI_START
{result['gitlab_ci']}
GITLABCI_END
_GENERATED_FILES_DATA_END_
"""
                else:
                    return f"Error generating pipeline: {result.get('detail', 'Unknown error')}"
        except Exception as e:
            return f"Error connecting to backend: {str(e)}"

    async def commit_pipeline_to_gitlab(
        self,
        repo_url: str,
        dockerfile_content: str,
        gitlab_ci_content: str,
        __user__: dict = {}
    ) -> str:
        """
        Commit the generated pipeline files to GitLab. Call this after user approves.

        :param repo_url: The GitLab repository URL
        :param dockerfile_content: Content of the Dockerfile
        :param gitlab_ci_content: Content of the .gitlab-ci.yml
        :return: Commit result with branch name and pipeline status
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/commit",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "gitlab_ci": gitlab_ci_content,
                        "dockerfile": dockerfile_content,
                        "commit_message": "Add CI/CD pipeline configuration [AI Generated]"
                    }
                )

                if response.status_code != 200:
                    return f"Error: Backend returned status {response.status_code}"

                # FIX: Handle None response
                result = response.json() or {}

                if result.get("success"):
                    return f"""## ✅ Files Committed Successfully!

**Branch:** `{result['branch']}`
**Commit ID:** `{result['commit_id']}`
**Web URL:** {result.get('web_url', 'N/A')}

🚀 **Pipeline has been triggered!**

The GitLab CI/CD pipeline is now running. You can:
1. Check the pipeline at: {result.get('web_url', 'GitLab project page')}
2. Ask me to "check pipeline status for {repo_url} branch {result['branch']}"
"""
                else:
                    return f"Error committing files: {result.get('detail', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def check_pipeline_status(
        self,
        repo_url: str,
        branch: str,
        __user__: dict = {}
    ) -> str:
        """
        Check the status of a GitLab CI/CD pipeline.

        :param repo_url: The GitLab repository URL
        :param branch: The branch name to check
        :return: Pipeline status and job details
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/status",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "branch": branch
                    }
                )

                # FIX: Handle None response
                result = response.json() or {}

                if result.get("success"):
                    status = result.get("status", "unknown")
                    emoji = {"success": "✅", "failed": "❌", "running": "🔄", "pending": "⏳"}.get(status, "❓")

                    output = f"""## Pipeline Status: {emoji} {status.upper()}

**Pipeline ID:** {result.get('pipeline_id', 'N/A')}
**Duration:** {result.get('duration', 'N/A')} seconds
**Web URL:** {result.get('web_url', 'N/A')}
"""
                    if result.get("failed_jobs"):
                        output += "\n### ❌ Failed Jobs:\n"
                        for job in result["failed_jobs"]:
                            output += f"- **{job['name']}** (stage: {job['stage']})\n"

                    return output
                else:
                    return f"Pipeline info: {result.get('message', 'No pipeline found')}"
        except Exception as e:
            return f"Error: {str(e)}"
