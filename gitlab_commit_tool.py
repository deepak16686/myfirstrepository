import textwrap, os
from open_webui.models.tools import Tools, ToolForm, ToolMeta
from open_webui.utils.plugin import load_tool_module_by_id, replace_imports
from open_webui.utils.tools import get_tool_specs
from open_webui.config import CACHE_DIR
from pathlib import Path

USER_ID = "1cc1b6fb-b86f-42fd-a51a-dfb70a7a0728"
TOOL_ID = "gitlab_commit_deploy"

content = replace_imports(textwrap.dedent('''
"""
description: Commit Dockerfile and .gitlab-ci.yml to GitLab and trigger pipeline
"""
import os, requests, json, time
from pydantic import BaseModel, Field
from urllib.parse import urlparse


def _gitlab_headers(token):
    return {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}


def _gitlab_get_project(base_url, token, project_name):
    url = f"{base_url}/api/v4/projects"
    resp = requests.get(url, headers=_gitlab_headers(token), params={"search": project_name}, timeout=10)
    if resp.status_code == 200:
        for p in resp.json():
            if p["name"] == project_name or p["path"] == project_name:
                return p
    return None


def _gitlab_create_project(base_url, token, project_name, branch):
    url = f"{base_url}/api/v4/projects"
    data = {
        "name": project_name,
        "visibility": "internal",
        "initialize_with_readme": True,
        "default_branch": branch
    }
    resp = requests.post(url, headers=_gitlab_headers(token), json=data, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _gitlab_get_project_by_path(base_url, token, project_path):
    encoded_path = requests.utils.quote(project_path.strip('/'), safe='')
    url = f"{base_url}/api/v4/projects/{encoded_path}"
    resp = requests.get(url, headers=_gitlab_headers(token), timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return None


def _parse_repo_url(repo_url):
    parsed = urlparse(repo_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("Invalid repo_url: missing scheme or hostname")
    project_path = parsed.path.strip('/')
    if '/-/' in project_path:
        project_path = project_path.split('/-/', 1)[0]
    if project_path.endswith('.git'):
        project_path = project_path[:-4]
    project_path = project_path.strip('/')
    if not project_path:
        raise ValueError("Invalid repo_url: could not determine project path")
    base_url = f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
    return base_url, project_path


class Tools:
    class Valves(BaseModel):
        GITLAB_URL: str = Field(
            default="http://gitlab-server",
            description="GitLab server URL (internal Docker network)"
        )
        GITLAB_TOKEN: str = Field(
            default="glpat-chatbot-deploy-2025",
            description="GitLab Personal Access Token with API scope"
        )
        DEFAULT_BRANCH: str = Field(
            default="main",
            description="Default branch name for new repositories"
        )

    def __init__(self):
        self.valves = self.Valves()

    def commit_and_deploy(self, project_name: str, dockerfile_content: str, gitlab_ci_content: str, commit_message: str = "Add Dockerfile and .gitlab-ci.yml", repo_url: str = "") -> str:
        """Commit Dockerfile and .gitlab-ci.yml to a GitLab repo and trigger the pipeline.
        project_name: Name of the GitLab project (used when repo_url is empty)
        repo_url: Full GitLab repository URL to commit into (takes precedence over project_name)
        dockerfile_content: The full Dockerfile content to commit
        gitlab_ci_content: The full .gitlab-ci.yml content to commit
        commit_message: Commit message (optional, defaults to 'Add Dockerfile and .gitlab-ci.yml')
        Returns the repository URL and pipeline URL."""
        try:
            base_url = self.valves.GITLAB_URL.rstrip('/')
            token = self.valves.GITLAB_TOKEN
            branch = self.valves.DEFAULT_BRANCH
            headers = _gitlab_headers(token)

            repo_url = (repo_url or "").strip()
            project_name = (project_name or "").strip()
            if not repo_url and not project_name:
                return "ERROR: Provide either repo_url or project_name so I know where to commit."

            # Step 1: Find target project (prefer repo_url when provided)
            if repo_url:
                try:
                    base_url, project_path = _parse_repo_url(repo_url)
                except ValueError as ve:
                    return f"ERROR: {ve}"
                project = _gitlab_get_project_by_path(base_url, token, project_path)
                if not project:
                    return f"ERROR: Repository not found or access denied: {repo_url}"
                project_id = project["id"]
                project_url = project["web_url"]
                status_msg = f"Using provided repository: {project_url}"
            else:
                project = _gitlab_get_project(base_url, token, project_name)
                if project:
                    project_id = project["id"]
                    project_url = project["web_url"]
                    status_msg = f"Using existing project: {project_name}"
                else:
                    project = _gitlab_create_project(base_url, token, project_name, branch)
                    project_id = project["id"]
                    project_url = project["web_url"]
                    status_msg = f"Created new project: {project_name}"
                    time.sleep(2)

            # Step 2: Build commit actions (create or update files)
            actions = []
            for file_path, file_content in [("Dockerfile", dockerfile_content), (".gitlab-ci.yml", gitlab_ci_content)]:
                check_url = f"{base_url}/api/v4/projects/{project_id}/repository/files/{requests.utils.quote(file_path, safe='')}"
                check_resp = requests.get(check_url, headers=headers, params={"ref": branch}, timeout=10)
                action = "update" if check_resp.status_code == 200 else "create"
                actions.append({
                    "action": action,
                    "file_path": file_path,
                    "content": file_content
                })

            # Step 3: Create commit with all files
            commit_url = f"{base_url}/api/v4/projects/{project_id}/repository/commits"
            commit_data = {
                "branch": branch,
                "commit_message": commit_message,
                "actions": actions
            }
            commit_resp = requests.post(commit_url, headers=headers, json=commit_data, timeout=15)
            commit_resp.raise_for_status()
            commit_info = commit_resp.json()
            commit_sha = commit_info.get("id", "unknown")[:8]

            # Step 4: Wait briefly and get pipeline status
            time.sleep(3)
            pipeline_url_api = f"{base_url}/api/v4/projects/{project_id}/pipelines"
            pipe_resp = requests.get(pipeline_url_api, headers=headers, params={"per_page": 1, "order_by": "id", "sort": "desc"}, timeout=10)
            pipeline_info = ""
            if pipe_resp.status_code == 200 and pipe_resp.json():
                pipeline = pipe_resp.json()[0]
                pipeline_info = f"\\n- Pipeline #{pipeline['id']}: {pipeline['status']}\\n- Pipeline URL: {pipeline['web_url']}"
            else:
                pipeline_info = "\\n- Pipeline: triggered (check GitLab for status)"

            return (
                f"## Deployment Successful!\\n\\n"
                f"- {status_msg}\\n"
                f"- Repository: {project_url}\\n"
                f"- Commit: {commit_sha}\\n"
                f"- Files committed: Dockerfile, .gitlab-ci.yml"
                f"{pipeline_info}"
            )

        except requests.exceptions.HTTPError as e:
            error_detail = e.response.text if e.response else str(e)
            return f"ERROR: GitLab API error: {e.response.status_code if e.response else 'unknown'} - {error_detail}"
        except requests.exceptions.ConnectionError:
            return f"ERROR: Cannot connect to GitLab at {base_url}. Ensure the server is running."
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {str(e)}"

    def list_projects(self) -> str:
        """List all available GitLab projects.
        Returns a list of project names and their URLs."""
        try:
            headers = _gitlab_headers(self.valves.GITLAB_TOKEN)
            url = f"{self.valves.GITLAB_URL}/api/v4/projects"
            resp = requests.get(url, headers=headers, params={"per_page": 50, "order_by": "updated_at"}, timeout=10)
            resp.raise_for_status()
            projects = resp.json()
            if not projects:
                return "No projects found in GitLab."
            lines = ["## GitLab Projects\\n"]
            for p in projects:
                lines.append(f"- **{p['name']}** ({p['path_with_namespace']}) - {p['web_url']}")
            return "\\n".join(lines)
        except Exception as e:
            return f"ERROR listing projects: {str(e)}"
''').strip())

meta = ToolMeta(description="Commit Dockerfile and .gitlab-ci.yml to GitLab and trigger CI/CD pipeline automatically")
form = ToolForm(id=TOOL_ID, name="GitLab Commit & Deploy", content=content, meta=meta, access_control=None)

existing = Tools.get_tool_by_id(TOOL_ID)
if existing:
    Tools.delete_tool_by_id(TOOL_ID)

module, frontmatter = load_tool_module_by_id(TOOL_ID, content=form.content)
form.meta.manifest = frontmatter
specs = get_tool_specs(module)
tool = Tools.insert_new_tool(USER_ID, form, specs)
(CACHE_DIR / "tools" / TOOL_ID).mkdir(parents=True, exist_ok=True)
print({"created": bool(tool), "id": TOOL_ID, "specs": specs})
