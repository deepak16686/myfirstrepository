"""
Secret Manager Service

Unified view/CRUD of secrets across GitLab CI/CD variables,
Gitea org secrets (2 orgs), and Jenkins credentials.
"""
import asyncio
from typing import Dict, Any, List, Optional

import httpx

from app.config import settings


class SecretManagerService:
    """Service for managing secrets across multiple platforms."""

    def _gitlab_headers(self) -> dict:
        return {"PRIVATE-TOKEN": settings.gitlab_token or "", "Content-Type": "application/json"}

    def _gitea_headers(self) -> dict:
        return {"Authorization": f"token {settings.github_token or ''}", "Accept": "application/json", "Content-Type": "application/json"}

    def _jenkins_auth(self) -> tuple:
        return (settings.jenkins_username or "admin", settings.jenkins_password or "")

    # ------------------------------------------------------------------
    # List all secrets
    # ------------------------------------------------------------------

    async def list_all(self) -> Dict[str, Any]:
        """List secrets from all platforms concurrently."""
        results = await asyncio.gather(
            self._list_gitlab_variables(),
            self._list_gitea_secrets("jenkins-projects"),
            self._list_gitea_secrets("github-projects"),
            self._list_jenkins_credentials(),
            return_exceptions=True,
        )

        def _unwrap(result, platform_name):
            if isinstance(result, Exception):
                return {"connected": False, "secrets": [], "error": str(result)}
            return result

        gitlab = _unwrap(results[0], "gitlab")
        gitea_jenkins = _unwrap(results[1], "gitea_jenkins")
        gitea_github = _unwrap(results[2], "gitea_github")
        jenkins = _unwrap(results[3], "jenkins")

        total = (len(gitlab.get("secrets", [])) + len(gitea_jenkins.get("secrets", []))
                 + len(gitea_github.get("secrets", [])) + len(jenkins.get("secrets", [])))

        return {
            "success": True,
            "platforms": {
                "gitlab": gitlab,
                "gitea_jenkins": gitea_jenkins,
                "gitea_github": gitea_github,
                "jenkins": jenkins,
            },
            "total_count": total,
        }

    async def _list_gitlab_variables(self) -> Dict[str, Any]:
        """List CI/CD variables from all GitLab projects."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{settings.gitlab_url}/api/v4/projects",
                params={"per_page": 100, "simple": "true"},
                headers=self._gitlab_headers(),
            )
            resp.raise_for_status()
            projects = resp.json()

            secrets = []
            for project in projects:
                pid = project.get("id")
                pname = project.get("path_with_namespace", project.get("name", str(pid)))
                try:
                    vresp = await client.get(
                        f"{settings.gitlab_url}/api/v4/projects/{pid}/variables",
                        headers=self._gitlab_headers(),
                    )
                    if vresp.status_code == 200:
                        for var in vresp.json():
                            secrets.append({
                                "platform": "gitlab",
                                "scope": f"project:{pname}",
                                "project_id": pid,
                                "key": var.get("key", ""),
                                "value": var.get("value", ""),
                                "protected": var.get("protected", False),
                                "masked": var.get("masked", False),
                                "environment_scope": var.get("environment_scope", "*"),
                                "variable_type": var.get("variable_type", "env_var"),
                            })
                except Exception:
                    continue

            return {"connected": True, "secrets": secrets}

    async def _list_gitea_secrets(self, org: str) -> Dict[str, Any]:
        """List org-level action secrets from Gitea."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{settings.github_url}/api/v1/orgs/{org}/actions/secrets",
                headers=self._gitea_headers(),
            )
            resp.raise_for_status()
            raw = resp.json()

            secrets = []
            for s in raw:
                secrets.append({
                    "platform": "gitea",
                    "scope": f"org:{org}",
                    "org": org,
                    "key": s.get("name", ""),
                    "value": "***",
                    "created_at": s.get("created_at", ""),
                })

            return {"connected": True, "org": org, "secrets": secrets}

    async def _list_jenkins_credentials(self) -> Dict[str, Any]:
        """List system credentials from Jenkins."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{settings.jenkins_url}/credentials/store/system/domain/_/api/json",
                params={"tree": "credentials[id,typeName,displayName,description]"},
                auth=self._jenkins_auth(),
            )
            resp.raise_for_status()
            data = resp.json()

            secrets = []
            for cred in data.get("credentials", []):
                secrets.append({
                    "platform": "jenkins",
                    "scope": "system",
                    "key": cred.get("id", ""),
                    "value": "***",
                    "display_name": cred.get("displayName", ""),
                    "type_name": cred.get("typeName", ""),
                    "description": cred.get("description", ""),
                })

            return {"connected": True, "secrets": secrets}

    # ------------------------------------------------------------------
    # GitLab projects list (for dropdown)
    # ------------------------------------------------------------------

    async def list_gitlab_projects(self) -> Dict[str, Any]:
        """List GitLab projects for the secret creation dropdown."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{settings.gitlab_url}/api/v4/projects",
                params={"per_page": 100, "simple": "true"},
                headers=self._gitlab_headers(),
            )
            resp.raise_for_status()
            projects = [
                {"id": p.get("id"), "name": p.get("name"), "name_with_namespace": p.get("path_with_namespace")}
                for p in resp.json()
            ]
            return {"success": True, "projects": projects}

    # ------------------------------------------------------------------
    # Create / Update / Delete
    # ------------------------------------------------------------------

    async def create_secret(self, platform: str, scope: str, key: str, value: str, **kwargs) -> Dict[str, Any]:
        """Create a secret on the specified platform."""
        try:
            if platform == "gitlab":
                return await self._create_gitlab_variable(scope, key, value, **kwargs)
            elif platform == "gitea":
                return await self._upsert_gitea_secret(scope, key, value)
            elif platform == "jenkins":
                return await self._create_jenkins_credential(key, value, **kwargs)
            else:
                return {"success": False, "error": f"Unknown platform: {platform}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def update_secret(self, platform: str, scope: str, key: str, value: str, **kwargs) -> Dict[str, Any]:
        """Update a secret on the specified platform."""
        try:
            if platform == "gitlab":
                return await self._update_gitlab_variable(scope, key, value, **kwargs)
            elif platform == "gitea":
                return await self._upsert_gitea_secret(scope, key, value)
            elif platform == "jenkins":
                # Jenkins: delete + recreate is simpler than config.xml manipulation
                await self._delete_jenkins_credential(key)
                return await self._create_jenkins_credential(key, value, **kwargs)
            else:
                return {"success": False, "error": f"Unknown platform: {platform}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def delete_secret(self, platform: str, scope: str, key: str) -> Dict[str, Any]:
        """Delete a secret from the specified platform."""
        try:
            if platform == "gitlab":
                return await self._delete_gitlab_variable(scope, key)
            elif platform == "gitea":
                return await self._delete_gitea_secret(scope, key)
            elif platform == "jenkins":
                return await self._delete_jenkins_credential(key)
            else:
                return {"success": False, "error": f"Unknown platform: {platform}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # GitLab CRUD helpers
    # ------------------------------------------------------------------

    def _parse_project_id(self, scope: str) -> int:
        """Extract project_id from scope like 'project:123' or 'project:root/app'."""
        _, _, val = scope.partition(":")
        try:
            return int(val)
        except ValueError:
            return val  # path_with_namespace works as project ID in GitLab API

    async def _create_gitlab_variable(self, scope: str, key: str, value: str, **kwargs) -> Dict[str, Any]:
        pid = self._parse_project_id(scope)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.gitlab_url}/api/v4/projects/{pid}/variables",
                headers=self._gitlab_headers(),
                json={
                    "key": key,
                    "value": value,
                    "protected": kwargs.get("protected", False),
                    "masked": kwargs.get("masked", False),
                    "environment_scope": kwargs.get("environment_scope", "*"),
                },
            )
            resp.raise_for_status()
            return {"success": True, "message": f"Variable '{key}' created in project {pid}"}

    async def _update_gitlab_variable(self, scope: str, key: str, value: str, **kwargs) -> Dict[str, Any]:
        pid = self._parse_project_id(scope)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(
                f"{settings.gitlab_url}/api/v4/projects/{pid}/variables/{key}",
                headers=self._gitlab_headers(),
                json={
                    "value": value,
                    "protected": kwargs.get("protected", False),
                    "masked": kwargs.get("masked", False),
                    "environment_scope": kwargs.get("environment_scope", "*"),
                },
            )
            resp.raise_for_status()
            return {"success": True, "message": f"Variable '{key}' updated in project {pid}"}

    async def _delete_gitlab_variable(self, scope: str, key: str) -> Dict[str, Any]:
        pid = self._parse_project_id(scope)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(
                f"{settings.gitlab_url}/api/v4/projects/{pid}/variables/{key}",
                headers=self._gitlab_headers(),
            )
            resp.raise_for_status()
            return {"success": True, "message": f"Variable '{key}' deleted from project {pid}"}

    # ------------------------------------------------------------------
    # Gitea CRUD helpers
    # ------------------------------------------------------------------

    def _parse_org(self, scope: str) -> str:
        """Extract org name from scope like 'org:jenkins-projects'."""
        _, _, org = scope.partition(":")
        return org

    async def _upsert_gitea_secret(self, scope: str, key: str, value: str) -> Dict[str, Any]:
        org = self._parse_org(scope)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.put(
                f"{settings.github_url}/api/v1/orgs/{org}/actions/secrets/{key}",
                headers=self._gitea_headers(),
                json={"data": value},
            )
            if resp.status_code in (200, 201, 204):
                return {"success": True, "message": f"Secret '{key}' saved in org {org}"}
            resp.raise_for_status()

    async def _delete_gitea_secret(self, scope: str, key: str) -> Dict[str, Any]:
        org = self._parse_org(scope)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.delete(
                f"{settings.github_url}/api/v1/orgs/{org}/actions/secrets/{key}",
                headers=self._gitea_headers(),
            )
            if resp.status_code in (200, 204):
                return {"success": True, "message": f"Secret '{key}' deleted from org {org}"}
            resp.raise_for_status()

    # ------------------------------------------------------------------
    # Jenkins CRUD helpers
    # ------------------------------------------------------------------

    async def _get_jenkins_crumb(self, client: httpx.AsyncClient) -> dict:
        """Fetch Jenkins CSRF crumb."""
        try:
            resp = await client.get(
                f"{settings.jenkins_url}/crumbIssuer/api/json",
                auth=self._jenkins_auth(),
            )
            if resp.status_code == 200:
                data = resp.json()
                return {data.get("crumbRequestField", "Jenkins-Crumb"): data.get("crumb", "")}
        except Exception:
            pass
        return {}

    async def _create_jenkins_credential(self, key: str, value: str, **kwargs) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            crumb_headers = await self._get_jenkins_crumb(client)
            import json as _json
            payload = {
                "": "0",
                "credentials": {
                    "scope": "GLOBAL",
                    "id": key,
                    "secret": value,
                    "description": kwargs.get("description", ""),
                    "$class": "org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl",
                },
            }
            resp = await client.post(
                f"{settings.jenkins_url}/credentials/store/system/domain/_/createCredentials",
                auth=self._jenkins_auth(),
                headers=crumb_headers,
                data={"json": _json.dumps(payload)},
            )
            if resp.status_code in (200, 302):
                return {"success": True, "message": f"Credential '{key}' created in Jenkins"}
            resp.raise_for_status()

    async def _delete_jenkins_credential(self, key: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            crumb_headers = await self._get_jenkins_crumb(client)
            resp = await client.post(
                f"{settings.jenkins_url}/credentials/store/system/domain/_/credential/{key}/doDelete",
                auth=self._jenkins_auth(),
                headers=crumb_headers,
            )
            if resp.status_code in (200, 302):
                return {"success": True, "message": f"Credential '{key}' deleted from Jenkins"}
            resp.raise_for_status()
