#!/usr/bin/env python3
"""
Install the GitLab Pipeline Generator tool into Open-WebUI
"""
import sqlite3
import json
import time

TOOL_CODE = '''"""
GitLab Pipeline Generator Tool for Open-WebUI
"""
import requests
from typing import Optional
from pydantic import BaseModel, Field


class Tools:
    """GitLab Pipeline Generator Tools"""

    class Valves(BaseModel):
        DEVOPS_BACKEND_URL: str = Field(
            default="http://host.docker.internal:8003",
            description="URL of the DevOps Tools Backend"
        )
        DEFAULT_GITLAB_TOKEN: str = Field(
            default="glpat-VLnGw2LEyscfJIcpKpposm86MQp1OjEH.01.0w1e224zy",
            description="Default GitLab access token"
        )

    def __init__(self):
        self.valves = self.Valves()

    def analyze_repository(self, repo_url: str, gitlab_token: Optional[str] = None) -> str:
        """
        Analyze a GitLab repository to understand its structure.
        :param repo_url: GitLab repository URL
        :param gitlab_token: GitLab access token (optional)
        :return: Analysis results
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/analyze",
                params={"repo_url": repo_url, "gitlab_token": token},
                timeout=30
            )
            data = response.json()
            if data.get("success"):
                a = data["analysis"]
                return f"Project: {a.get('project_name')}\\nLanguage: {a.get('language')}\\nFramework: {a.get('framework')}\\nHas Dockerfile: {a.get('has_dockerfile')}\\nHas .gitlab-ci.yml: {a.get('has_gitlab_ci')}"
            return f"Error: {data.get('message')}"
        except Exception as e:
            return f"Error: {str(e)}"

    def generate_pipeline(self, repo_url: str, additional_requirements: Optional[str] = None, gitlab_token: Optional[str] = None) -> str:
        """
        Generate .gitlab-ci.yml and Dockerfile for a repository.
        :param repo_url: GitLab repository URL
        :param additional_requirements: Extra requirements
        :param gitlab_token: GitLab access token
        :return: Generated files
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/generate",
                json={"repo_url": repo_url, "gitlab_token": token, "additional_context": additional_requirements or "", "model": "qwen2.5-coder:32b-instruct-q4_K_M"},
                timeout=120
            )
            data = response.json()
            if data.get("success"):
                return f".gitlab-ci.yml:\\n```yaml\\n{data['gitlab_ci']}\\n```\\n\\nDockerfile:\\n```dockerfile\\n{data['dockerfile']}\\n```"
            return f"Error: {data.get('message')}"
        except Exception as e:
            return f"Error: {str(e)}"

    def commit_pipeline(self, repo_url: str, gitlab_ci_content: str, dockerfile_content: str, branch_name: Optional[str] = None, gitlab_token: Optional[str] = None) -> str:
        """
        Commit generated files to a new branch.
        :param repo_url: GitLab repository URL
        :param gitlab_ci_content: .gitlab-ci.yml content
        :param dockerfile_content: Dockerfile content
        :param branch_name: Branch name
        :param gitlab_token: GitLab access token
        :return: Commit result
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/commit",
                json={"repo_url": repo_url, "gitlab_token": token, "gitlab_ci": gitlab_ci_content, "dockerfile": dockerfile_content, "branch_name": branch_name},
                timeout=60
            )
            data = response.json()
            if data.get("success"):
                return f"Committed to branch: {data['branch']}\\nCommit: {data['commit_id']}\\nPipeline triggered!"
            return f"Error: {data.get('message')}"
        except Exception as e:
            return f"Error: {str(e)}"

    def check_pipeline_status(self, repo_url: str, branch: str, gitlab_token: Optional[str] = None) -> str:
        """
        Check pipeline status for a branch.
        :param repo_url: GitLab repository URL
        :param branch: Branch name
        :param gitlab_token: GitLab access token
        :return: Pipeline status
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/status",
                json={"repo_url": repo_url, "gitlab_token": token, "branch": branch},
                timeout=30
            )
            data = response.json()
            return f"Status: {data.get('status', 'unknown').upper()}"
        except Exception as e:
            return f"Error: {str(e)}"

    def full_workflow(self, repo_url: str, requirements: Optional[str] = None, gitlab_token: Optional[str] = None) -> str:
        """
        Complete workflow: Analyze -> Generate -> Commit.
        :param repo_url: GitLab repository URL
        :param requirements: Additional requirements
        :param gitlab_token: GitLab access token
        :return: Workflow results
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/workflow",
                json={"repo_url": repo_url, "gitlab_token": token, "additional_context": requirements or "", "model": "qwen2.5-coder:32b-instruct-q4_K_M", "auto_commit": True},
                timeout=180
            )
            data = response.json()
            if data.get("success"):
                gen = data.get("generation", {})
                commit = data.get("commit", {})
                return f"Language: {gen.get('analysis', {}).get('language')}\\nBranch: {commit.get('branch')}\\nPipeline triggered!"
            return f"Error: {data.get('message')}"
        except Exception as e:
            return f"Error: {str(e)}"

    def store_feedback(self, repo_url: str, branch: str, original_gitlab_ci: str, original_dockerfile: str, error_type: str, fix_description: str, gitlab_token: Optional[str] = None) -> str:
        """
        Store feedback for reinforcement learning after fixes.
        :param repo_url: GitLab repository URL
        :param branch: Branch with fixes
        :param original_gitlab_ci: Original .gitlab-ci.yml
        :param original_dockerfile: Original Dockerfile
        :param error_type: Type of error fixed
        :param fix_description: Description of fix
        :param gitlab_token: GitLab access token
        :return: Feedback storage result
        """
        token = gitlab_token or self.valves.DEFAULT_GITLAB_TOKEN
        try:
            response = requests.post(
                f"{self.valves.DEVOPS_BACKEND_URL}/api/v1/pipeline/feedback",
                json={"repo_url": repo_url, "gitlab_token": token, "branch": branch, "original_gitlab_ci": original_gitlab_ci, "original_dockerfile": original_dockerfile, "error_type": error_type, "fix_description": fix_description},
                timeout=30
            )
            data = response.json()
            if data.get("success"):
                return "Feedback stored for reinforcement learning!"
            return f"Error: {data.get('message')}"
        except Exception as e:
            return f"Error: {str(e)}"
'''

def main():
    conn = sqlite3.connect('/app/backend/data/webui.db')
    c = conn.cursor()

    tool_id = 'gitlab-pipeline-generator'
    name = 'GitLab Pipeline Generator'
    now = int(time.time())

    meta = {
        'description': 'Generate CI/CD pipelines and Dockerfiles for GitLab repositories with reinforcement learning'
    }

    c.execute('SELECT id FROM tool WHERE id=?', (tool_id,))
    existing = c.fetchone()

    if existing:
        c.execute('UPDATE tool SET name=?, content=?, meta=?, updated_at=? WHERE id=?',
                  (name, TOOL_CODE, json.dumps(meta), now, tool_id))
        print(f'Updated existing tool: {tool_id}')
    else:
        c.execute('INSERT INTO tool (id, name, content, meta, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (tool_id, name, TOOL_CODE, json.dumps(meta), now, now, '1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728'))
        print(f'Created new tool: {tool_id}')

    conn.commit()
    conn.close()
    print('Done!')


if __name__ == '__main__':
    main()
