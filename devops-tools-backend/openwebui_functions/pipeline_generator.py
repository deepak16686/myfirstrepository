"""
Open WebUI Function: GitLab Pipeline Generator
This function enables the chatbot to automatically generate and commit CI/CD pipelines.

To install:
1. Go to Open WebUI -> Workspace -> Functions
2. Click "+" to add new function
3. Paste this code
4. Save and enable the function
"""

import json
import httpx
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Tools:
    """Pipeline Generator Tools for Open WebUI"""

    class Valves(BaseModel):
        """Configuration for the pipeline generator"""
        BACKEND_URL: str = Field(
            default="http://devops-tools-backend:8003",
            description="DevOps Tools Backend URL"
        )
        GITLAB_TOKEN: str = Field(
            default="",
            description="GitLab API Token"
        )

    def __init__(self):
        self.valves = self.Valves()

    async def analyze_repository(
        self,
        repo_url: str,
        __user__: dict = {}
    ) -> str:
        """
        Analyze a GitLab repository to detect language and framework.

        :param repo_url: GitLab repository URL (e.g., http://gitlab-server/root/my-project.git)
        :return: Analysis results including detected language and framework
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/analyze",
                    params={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN
                    }
                )
                # FIX: Handle None response
                result = response.json() or {}

                if result.get("success"):
                    analysis = result["analysis"]
                    return f"""
## Repository Analysis Complete

**Project:** {analysis.get('project_name', 'Unknown')}
**Language:** {analysis.get('language', 'Unknown')}
**Framework:** {analysis.get('framework', 'Unknown')}
**Package Manager:** {analysis.get('package_manager', 'Unknown')}
**Has Dockerfile:** {analysis.get('has_dockerfile', False)}
**Has GitLab CI:** {analysis.get('has_gitlab_ci', False)}

Files detected: {', '.join(analysis.get('files', [])[:10])}

Would you like me to generate the CI/CD pipeline for this project?
"""
                else:
                    return f"Error analyzing repository: {result}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def generate_pipeline(
        self,
        repo_url: str,
        additional_context: str = "",
        __user__: dict = {}
    ) -> str:
        """
        Generate .gitlab-ci.yml and Dockerfile for a repository.

        :param repo_url: GitLab repository URL
        :param additional_context: Optional additional requirements
        :return: Generated pipeline files for approval
        """
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/generate",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "additional_context": additional_context,
                        "model": "pipeline-generator-v5"
                    }
                )
                # FIX: Handle None response
                result = response.json() or {}

                if result.get("success"):
                    return f"""
## Generated Pipeline Files

### Analysis
- **Language:** {result['analysis'].get('language')}
- **Framework:** {result['analysis'].get('framework')}
- **Model Used:** {result.get('model_used')}

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
Reply with **"yes"** or **"approve"** to commit, or **"no"** to cancel.
"""
                else:
                    return f"Error generating pipeline: {result}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def commit_pipeline(
        self,
        repo_url: str,
        gitlab_ci: str,
        dockerfile: str,
        branch_name: str = "",
        __user__: dict = {}
    ) -> str:
        """
        Commit generated pipeline files to GitLab repository.

        :param repo_url: GitLab repository URL
        :param gitlab_ci: Content of .gitlab-ci.yml
        :param dockerfile: Content of Dockerfile
        :param branch_name: Optional branch name (auto-generated if empty)
        :return: Commit result with branch and pipeline info
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "repo_url": repo_url,
                    "gitlab_token": self.valves.GITLAB_TOKEN,
                    "gitlab_ci": gitlab_ci,
                    "dockerfile": dockerfile,
                    "commit_message": "Add CI/CD pipeline configuration [AI Generated]"
                }
                if branch_name:
                    payload["branch_name"] = branch_name

                response = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/commit",
                    json=payload
                )
                # FIX: Handle None response
                result = response.json() or {}

                if result.get("success"):
                    return f"""
## ✅ Files Committed Successfully!

**Branch:** `{result['branch']}`
**Commit ID:** `{result['commit_id']}`
**Project ID:** {result['project_id']}

🚀 **Pipeline triggered automatically!**

I'm now monitoring the pipeline status...
"""
                else:
                    return f"Error committing files: {result}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def check_pipeline_status(
        self,
        repo_url: str,
        branch: str,
        __user__: dict = {}
    ) -> str:
        """
        Check the status of a GitLab pipeline.

        :param repo_url: GitLab repository URL
        :param branch: Branch name to check
        :return: Pipeline status and details
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
                    status_emoji = {
                        "success": "✅",
                        "failed": "❌",
                        "running": "🔄",
                        "pending": "⏳",
                        "canceled": "🚫"
                    }.get(status, "❓")

                    output = f"""
## Pipeline Status: {status_emoji} {status.upper()}

**Pipeline ID:** {result.get('pipeline_id')}
**Duration:** {result.get('duration', 'N/A')} seconds
**Web URL:** {result.get('web_url', 'N/A')}
"""

                    if result.get("failed_jobs"):
                        output += "\n### Failed Jobs:\n"
                        for job in result["failed_jobs"]:
                            output += f"- **{job['name']}** (stage: {job['stage']})\n"

                    return output
                else:
                    return f"Pipeline status: {result.get('message', 'Unknown')}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def full_workflow(
        self,
        repo_url: str,
        additional_context: str = "",
        __user__: dict = {}
    ) -> str:
        """
        Complete workflow: Analyze -> Generate -> Commit -> Monitor pipeline.

        :param repo_url: GitLab repository URL
        :param additional_context: Optional additional requirements
        :return: Complete workflow result
        """
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{self.valves.BACKEND_URL}/pipeline/workflow",
                    json={
                        "repo_url": repo_url,
                        "gitlab_token": self.valves.GITLAB_TOKEN,
                        "additional_context": additional_context,
                        "model": "pipeline-generator-v5",
                        "auto_commit": True
                    }
                )
                # FIX: Handle None response
                result = response.json() or {}

                if result.get("success"):
                    gen = result["generation"]
                    commit = result.get("commit", {})

                    return f"""
## 🎉 Pipeline Generation Complete!

### Repository Analysis
- **Language:** {gen['analysis'].get('language')}
- **Framework:** {gen['analysis'].get('framework')}

### Generated Files

**Dockerfile:**
```dockerfile
{gen['dockerfile']}
```

**.gitlab-ci.yml:**
```yaml
{gen['gitlab_ci'][:2000]}...
```

### Commit Info
- **Branch:** `{commit.get('branch', 'N/A')}`
- **Commit ID:** `{commit.get('commit_id', 'N/A')}`

### 🚀 Pipeline Started!
Use "check pipeline status for {repo_url} branch {commit.get('branch', '')}" to monitor progress.
"""
                else:
                    return f"Error in workflow: {result}"
        except Exception as e:
            return f"Error: {str(e)}"
