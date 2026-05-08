"""
GitLab Pipeline Generator Tool for Open-WebUI

This tool enables AI models in Open-WebUI to:
1. Analyze GitLab repositories
2. Generate CI/CD pipelines and Dockerfiles
3. Commit to repositories
4. Monitor pipeline status
5. Store feedback for reinforcement learning

To use this tool:
1. Go to Open-WebUI Admin Panel -> Workspace -> Tools
2. Click "+" to add a new tool
3. Paste this code
4. Save and enable the tool
"""
import requests
from typing import Optional
from pydantic import BaseModel, Field


class Tools:
    """GitLab Pipeline Generator Tools"""

    class Valves(BaseModel):
        """Configuration for the tool"""
        DEVOPS_BACKEND_URL: str = Field(
            default="http://host.docker.internal:8003",
            description="URL of the DevOps Tools Backend"
        )
        DEFAULT_GITLAB_TOKEN: str = Field(
            default="",
            description="Default GitLab access token (can be overridden per request)"
        )

    def __init__(self):
        self.valves = self.Valves()

    def analyze_repository(
        self,
        repo_url: str,
        gitlab_token: Optional[str] = None
    ) -> str:
        """
        Analyze a GitLab repository to understand its structure.

        Args:
            repo_url: GitLab repository URL (e.g., http://localhost:8929/user/repo)
            gitlab_token: GitLab access token (optional, uses default if not provided)

        Returns:
            Analysis including detected language, framework, and existing files
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        if not token:
            return "Error: GitLab token not provided. Please provide a token or configure the default token in tool settings."

        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/analyze",
                params={"repo_url": repo_url, "gitlab_token": token},
                timeout=30
            )
            response.raise_for_status()
            # FIX: Handle None response
            data = response.json() or {}

            if data.get("success"):
                analysis = data["analysis"]
                return f"""## Repository Analysis

**Project:** {analysis.get('project_name', 'Unknown')}
**Language:** {analysis.get('language', 'Unknown')}
**Framework:** {analysis.get('framework', 'Unknown')}
**Package Manager:** {analysis.get('package_manager', 'Unknown')}
**Default Branch:** {analysis.get('default_branch', 'main')}

**Existing Files:**
- Has Dockerfile: {'Yes' if analysis.get('has_dockerfile') else 'No'}
- Has .gitlab-ci.yml: {'Yes' if analysis.get('has_gitlab_ci') else 'No'}

**Files in Repository:**
{', '.join(analysis.get('files', [])[:15])}
"""
            else:
                return f"Error analyzing repository: {data.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"

    def generate_pipeline(
        self,
        repo_url: str,
        additional_requirements: Optional[str] = None,
        gitlab_token: Optional[str] = None
    ) -> str:
        """
        Generate .gitlab-ci.yml and Dockerfile for a repository.

        Args:
            repo_url: GitLab repository URL
            additional_requirements: Extra requirements for the pipeline (e.g., "add SonarQube scanning", "deploy to Kubernetes")
            gitlab_token: GitLab access token

        Returns:
            Generated .gitlab-ci.yml and Dockerfile content
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        if not token:
            return "Error: GitLab token not provided."

        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/generate",
                json={
                    "repo_url": repo_url,
                    "gitlab_token": token,
                    "additional_context": additional_requirements or "",
                    "model": "qwen2.5-coder:32b-instruct-q4_K_M"
                },
                timeout=120
            )
            response.raise_for_status()
            # FIX: Handle None response
            data = response.json() or {}

            if data.get("success"):
                return f"""## Generated Pipeline Files

### Analysis
- **Language:** {data['analysis'].get('language')}
- **Framework:** {data['analysis'].get('framework')}
- **Feedback Used:** {data.get('feedback_used', 0)} previous corrections applied

---

### .gitlab-ci.yml

```yaml
{data['gitlab_ci']}
```

---

### Dockerfile

```dockerfile
{data['dockerfile']}
```

---

**Next Steps:**
1. Review the generated files above
2. If they look good, use `commit_pipeline` to commit them to the repository
3. Or ask me to modify specific parts before committing
"""
            else:
                return f"Error generating pipeline: {data.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"

    def commit_pipeline(
        self,
        repo_url: str,
        gitlab_ci_content: str,
        dockerfile_content: str,
        branch_name: Optional[str] = None,
        gitlab_token: Optional[str] = None
    ) -> str:
        """
        Commit generated pipeline files to a new branch in GitLab.

        Args:
            repo_url: GitLab repository URL
            gitlab_ci_content: Content for .gitlab-ci.yml
            dockerfile_content: Content for Dockerfile
            branch_name: Name for the new branch (auto-generated if not provided)
            gitlab_token: GitLab access token

        Returns:
            Commit result with branch name and pipeline status
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        if not token:
            return "Error: GitLab token not provided."

        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/commit",
                json={
                    "repo_url": repo_url,
                    "gitlab_token": token,
                    "gitlab_ci": gitlab_ci_content,
                    "dockerfile": dockerfile_content,
                    "branch_name": branch_name,
                    "commit_message": "Add CI/CD pipeline configuration [AI Generated]"
                },
                timeout=60
            )
            response.raise_for_status()
            # FIX: Handle None response
            data = response.json() or {}

            if data.get("success"):
                return f"""## Commit Successful!

**Branch:** `{data['branch']}`
**Commit ID:** `{data['commit_id']}`
**Web URL:** {data.get('web_url', 'N/A')}

🚀 **Pipeline has been triggered!**

The CI/CD pipeline should start automatically. Use `check_pipeline_status` to monitor its progress.

**Next Steps:**
1. Check pipeline status: `check_pipeline_status("{repo_url}", "{data['branch']}")`
2. If the pipeline fails, a DevOps engineer can fix it
3. After fixing, use `store_feedback` to help me learn from the correction
"""
            else:
                return f"Error committing: {data.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"

    def check_pipeline_status(
        self,
        repo_url: str,
        branch: str,
        gitlab_token: Optional[str] = None
    ) -> str:
        """
        Check the status of the latest pipeline for a branch.

        Args:
            repo_url: GitLab repository URL
            branch: Branch name to check
            gitlab_token: GitLab access token

        Returns:
            Pipeline status including job details
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        if not token:
            return "Error: GitLab token not provided."

        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/status",
                json={
                    "repo_url": repo_url,
                    "gitlab_token": token,
                    "branch": branch
                },
                timeout=30
            )
            response.raise_for_status()
            # FIX: Handle None response
            data = response.json() or {}

            if data.get("success"):
                status = data.get("status", "unknown")
                status_emoji = {
                    "success": "✅",
                    "failed": "❌",
                    "running": "🔄",
                    "pending": "⏳",
                    "canceled": "🚫"
                }.get(status, "❓")

                result = f"""## Pipeline Status

**Status:** {status_emoji} {status.upper()}
**Pipeline ID:** {data.get('pipeline_id', 'N/A')}
**Web URL:** {data.get('web_url', 'N/A')}
**Duration:** {data.get('duration', 'N/A')} seconds
"""

                if data.get("failed_jobs"):
                    result += "\n### Failed Jobs:\n"
                    for job in data["failed_jobs"]:
                        result += f"- **{job['name']}** (stage: {job['stage']})\n"
                    result += "\n⚠️ Please ask a DevOps engineer to review and fix the failed jobs."
                    result += "\nAfter fixing, use `store_feedback` to help me learn from the correction."

                return result
            else:
                return f"Pipeline status: {data.get('message', 'No pipeline found')}"
        except Exception as e:
            return f"Error: {str(e)}"

    def store_feedback(
        self,
        repo_url: str,
        branch: str,
        original_gitlab_ci: str,
        original_dockerfile: str,
        error_type: str,
        fix_description: str,
        gitlab_token: Optional[str] = None
    ) -> str:
        """
        Store feedback after a DevOps engineer fixes the pipeline.
        This helps the AI learn from corrections (reinforcement learning).

        Args:
            repo_url: GitLab repository URL
            branch: Branch with the fixes
            original_gitlab_ci: The originally generated .gitlab-ci.yml
            original_dockerfile: The originally generated Dockerfile
            error_type: Type of error that was fixed (e.g., "syntax_error", "missing_dependency", "wrong_base_image")
            fix_description: Description of what was fixed
            gitlab_token: GitLab access token

        Returns:
            Confirmation that feedback was stored
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        if not token:
            return "Error: GitLab token not provided."

        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/feedback",
                json={
                    "repo_url": repo_url,
                    "gitlab_token": token,
                    "branch": branch,
                    "original_gitlab_ci": original_gitlab_ci,
                    "original_dockerfile": original_dockerfile,
                    "error_type": error_type,
                    "fix_description": fix_description
                },
                timeout=30
            )
            response.raise_for_status()
            # FIX: Handle None response
            data = response.json() or {}

            if data.get("success"):
                return f"""## Feedback Stored Successfully!

**Changes Detected:**
- .gitlab-ci.yml: {'Yes' if data.get('changes_detected', {}).get('gitlab_ci') else 'No'}
- Dockerfile: {'Yes' if data.get('changes_detected', {}).get('dockerfile') else 'No'}

🧠 **Thank you!** This feedback will help me generate better pipelines in the future.
I'll remember to avoid "{error_type}" errors and apply similar fixes automatically.
"""
            else:
                return f"Error storing feedback: {data.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"

    def full_workflow(
        self,
        repo_url: str,
        requirements: Optional[str] = None,
        gitlab_token: Optional[str] = None
    ) -> str:
        """
        Complete workflow: Analyze -> Generate -> Commit in one step.

        Args:
            repo_url: GitLab repository URL
            requirements: Additional requirements for the pipeline
            gitlab_token: GitLab access token

        Returns:
            Complete workflow results including generated files and commit info
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        if not token:
            return "Error: GitLab token not provided."

        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/workflow",
                json={
                    "repo_url": repo_url,
                    "gitlab_token": token,
                    "additional_context": requirements or "",
                    "model": "qwen2.5-coder:32b-instruct-q4_K_M",
                    "auto_commit": True
                },
                timeout=180
            )
            response.raise_for_status()
            # FIX: Handle None response
            data = response.json() or {}

            if data.get("success"):
                gen = data.get("generation", {})
                commit = data.get("commit", {})

                result = f"""## Complete Workflow Executed!

### 1. Repository Analysis
- **Language:** {gen.get('analysis', {}).get('language', 'Unknown')}
- **Framework:** {gen.get('analysis', {}).get('framework', 'Unknown')}
- **Feedback Applied:** {gen.get('feedback_used', 0)} previous corrections

### 2. Generated Files

#### .gitlab-ci.yml
```yaml
{gen.get('gitlab_ci', 'N/A')[:1000]}...
```

#### Dockerfile
```dockerfile
{gen.get('dockerfile', 'N/A')[:500]}...
```

### 3. Commit Info
- **Branch:** `{commit.get('branch', 'N/A')}`
- **Commit ID:** `{commit.get('commit_id', 'N/A')}`

### 4. Pipeline Status
🚀 Pipeline triggered! Use `check_pipeline_status` to monitor.

**Monitor with:**
```
check_pipeline_status("{repo_url}", "{commit.get('branch', 'N/A')}")
```
"""
                return result
            else:
                return f"Error in workflow: {data.get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error: {str(e)}"
