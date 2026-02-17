"""
RBAC Service - Aggregates access data from all DevOps tools

Queries each tool's API using admin credentials (from Vault) to:
- List users and their group memberships across all tools
- Grant/revoke group access per tool
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any

import httpx

from app.config import settings
from app.integrations.vault_client import vault

logger = logging.getLogger(__name__)

# Group name → display label
GROUP_LABELS = {
    "devops-readonly": "Read Only",
    "devops-readwrite": "Read/Write",
    "devops-admin": "Admin",
}

TOOLS = ["gitlab", "gitea", "sonarqube", "nexus", "jenkins"]


def _get_admin_creds() -> Dict[str, Any]:
    """Get admin credentials for each tool from Vault (admin path, not service-account)."""
    return {
        "gitlab": {
            "url": settings.gitlab_url,
            "token": vault.get_secret("gitlab", "token") or settings.gitlab_token or "",
        },
        "gitea": {
            "url": settings.github_url,  # Gitea serves as GitHub
            "token": vault.get_secret("gitea", "token") or settings.github_token or "",
        },
        "sonarqube": {
            "url": settings.sonarqube_url,
            "password": vault.get_secret("sonarqube", "password") or settings.sonarqube_password or "",
        },
        "nexus": {
            "url": settings.nexus_url,
            "username": vault.get_secret("nexus", "username") or settings.nexus_username or "admin",
            "password": vault.get_secret("nexus", "password") or settings.nexus_password or "",
        },
        "jenkins": {
            "url": settings.jenkins_url,
            "username": vault.get_secret("jenkins", "username") or settings.jenkins_username or "admin",
            "password": vault.get_secret("jenkins", "password") or settings.jenkins_password or "",
        },
    }


# ============================================================
# GitLab
# ============================================================

async def _gitlab_get_users_and_groups(creds: dict) -> Dict[str, Any]:
    """Get all GitLab users and their devops-* group memberships."""
    url = creds["url"]
    headers = {"PRIVATE-TOKEN": creds["token"]}
    result = {"users": {}, "groups": {}}

    if not creds["token"]:
        return result

    async with httpx.AsyncClient(timeout=15) as client:
        # Get devops groups
        try:
            resp = await client.get(f"{url}/api/v4/groups", headers=headers, params={"per_page": 100})
            all_groups = resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.warning(f"GitLab groups fetch failed: {e}")
            return result

        devops_groups = [g for g in all_groups if g.get("path", "").startswith("devops-")]

        for group in devops_groups:
            gname = group["path"]
            gid = group["id"]
            result["groups"][gname] = {"id": gid, "members": []}

            try:
                resp = await client.get(f"{url}/api/v4/groups/{gid}/members", headers=headers, params={"per_page": 100})
                members = resp.json() if resp.status_code == 200 else []
            except Exception:
                members = []

            for m in members:
                username = m.get("username", "")
                result["groups"][gname]["members"].append(username)
                if username not in result["users"]:
                    result["users"][username] = {"display_name": m.get("name", username), "groups": []}
                result["users"][username]["groups"].append(gname)

        # Also get users not in any devops group
        try:
            resp = await client.get(f"{url}/api/v4/users", headers=headers, params={"per_page": 100, "active": True})
            all_users = resp.json() if resp.status_code == 200 else []
            for u in all_users:
                uname = u.get("username", "")
                if uname and uname not in result["users"]:
                    result["users"][uname] = {"display_name": u.get("name", uname), "groups": []}
        except Exception:
            pass

    return result


async def _gitlab_grant(creds: dict, username: str, group: str) -> dict:
    """Add user to a GitLab group."""
    url = creds["url"]
    headers = {"PRIVATE-TOKEN": creds["token"], "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=15) as client:
        # Get user ID
        resp = await client.get(f"{url}/api/v4/users", headers=headers, params={"username": username})
        users = resp.json() if resp.status_code == 200 else []
        if not users:
            return {"success": False, "message": f"User '{username}' not found in GitLab"}
        user_id = users[0]["id"]

        # Get group ID
        resp = await client.get(f"{url}/api/v4/groups", headers=headers, params={"search": group})
        groups = [g for g in (resp.json() if resp.status_code == 200 else []) if g.get("path") == group]
        if not groups:
            return {"success": False, "message": f"Group '{group}' not found in GitLab"}
        group_id = groups[0]["id"]

        # Access level: admin=40, readwrite=30, readonly=20
        access_map = {"devops-admin": 40, "devops-readwrite": 30, "devops-readonly": 20}
        access_level = access_map.get(group, 30)

        resp = await client.post(
            f"{url}/api/v4/groups/{group_id}/members",
            headers=headers,
            json={"user_id": user_id, "access_level": access_level}
        )
        if resp.status_code in (200, 201):
            return {"success": True, "message": f"Added to {group}"}
        elif resp.status_code == 409:
            return {"success": True, "message": f"Already in {group}"}
        return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text}"}


async def _gitlab_revoke(creds: dict, username: str, group: str) -> dict:
    """Remove user from a GitLab group."""
    url = creds["url"]
    headers = {"PRIVATE-TOKEN": creds["token"]}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{url}/api/v4/users", headers=headers, params={"username": username})
        users = resp.json() if resp.status_code == 200 else []
        if not users:
            return {"success": False, "message": f"User '{username}' not found"}
        user_id = users[0]["id"]

        resp = await client.get(f"{url}/api/v4/groups", headers=headers, params={"search": group})
        groups = [g for g in (resp.json() if resp.status_code == 200 else []) if g.get("path") == group]
        if not groups:
            return {"success": False, "message": f"Group '{group}' not found"}
        group_id = groups[0]["id"]

        resp = await client.delete(f"{url}/api/v4/groups/{group_id}/members/{user_id}", headers=headers)
        if resp.status_code in (200, 204):
            return {"success": True, "message": f"Removed from {group}"}
        return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text}"}


# ============================================================
# Gitea
# ============================================================

async def _gitea_get_users_and_groups(creds: dict) -> Dict[str, Any]:
    """Get Gitea users and their devops-* team memberships across orgs."""
    url = creds["url"]
    headers = {"Authorization": f"token {creds['token']}"}
    result = {"users": {}, "groups": {}}

    if not creds["token"]:
        return result

    async with httpx.AsyncClient(timeout=15) as client:
        for org in ["jenkins-projects", "github-projects"]:
            try:
                resp = await client.get(f"{url}/api/v1/orgs/{org}/teams", headers=headers)
                teams = resp.json() if resp.status_code == 200 else []
            except Exception as e:
                logger.warning(f"Gitea teams fetch for {org} failed: {e}")
                continue

            for team in teams:
                tname = team.get("name", "")
                if not tname.startswith("devops-"):
                    continue
                tid = team["id"]

                if tname not in result["groups"]:
                    result["groups"][tname] = {"id": tid, "members": [], "team_ids": {}}
                result["groups"][tname]["team_ids"][org] = tid

                try:
                    resp = await client.get(f"{url}/api/v1/teams/{tid}/members", headers=headers)
                    members = resp.json() if resp.status_code == 200 else []
                except Exception:
                    members = []

                for m in members:
                    uname = m.get("login", "")
                    if uname not in result["groups"][tname]["members"]:
                        result["groups"][tname]["members"].append(uname)
                    if uname not in result["users"]:
                        result["users"][uname] = {"display_name": m.get("full_name") or uname, "groups": []}
                    if tname not in result["users"][uname]["groups"]:
                        result["users"][uname]["groups"].append(tname)

        # Get all users
        try:
            resp = await client.get(f"{url}/api/v1/admin/users", headers=headers, params={"limit": 50})
            all_users = resp.json() if resp.status_code == 200 else []
            for u in all_users:
                uname = u.get("login", "")
                if uname and uname not in result["users"]:
                    result["users"][uname] = {"display_name": u.get("full_name") or uname, "groups": []}
        except Exception:
            pass

    return result


async def _gitea_grant(creds: dict, username: str, group: str) -> dict:
    """Add user to Gitea team in all orgs."""
    url = creds["url"]
    headers = {"Authorization": f"token {creds['token']}"}
    added = []

    async with httpx.AsyncClient(timeout=15) as client:
        for org in ["jenkins-projects", "github-projects"]:
            resp = await client.get(f"{url}/api/v1/orgs/{org}/teams", headers=headers)
            teams = [t for t in (resp.json() if resp.status_code == 200 else []) if t.get("name") == group]
            for team in teams:
                resp = await client.put(f"{url}/api/v1/teams/{team['id']}/members/{username}", headers=headers)
                if resp.status_code in (200, 204):
                    added.append(f"{org}/{group}")

    if added:
        return {"success": True, "message": f"Added to {', '.join(added)}"}
    return {"success": False, "message": f"Team '{group}' not found or user cannot be added"}


async def _gitea_revoke(creds: dict, username: str, group: str) -> dict:
    """Remove user from Gitea team in all orgs."""
    url = creds["url"]
    headers = {"Authorization": f"token {creds['token']}"}
    removed = []

    async with httpx.AsyncClient(timeout=15) as client:
        for org in ["jenkins-projects", "github-projects"]:
            resp = await client.get(f"{url}/api/v1/orgs/{org}/teams", headers=headers)
            teams = [t for t in (resp.json() if resp.status_code == 200 else []) if t.get("name") == group]
            for team in teams:
                resp = await client.delete(f"{url}/api/v1/teams/{team['id']}/members/{username}", headers=headers)
                if resp.status_code in (200, 204):
                    removed.append(f"{org}/{group}")

    if removed:
        return {"success": True, "message": f"Removed from {', '.join(removed)}"}
    return {"success": False, "message": f"Team '{group}' not found or user not a member"}


# ============================================================
# SonarQube
# ============================================================

async def _sonarqube_get_users_and_groups(creds: dict) -> Dict[str, Any]:
    """Get SonarQube users and their devops-* group memberships."""
    url = creds["url"]
    auth = ("admin", creds["password"])
    result = {"users": {}, "groups": {}}

    if not creds["password"]:
        return result

    async with httpx.AsyncClient(timeout=15) as client:
        # Get groups
        try:
            resp = await client.get(f"{url}/api/user_groups/search", auth=auth, params={"ps": 100})
            all_groups = (resp.json() if resp.status_code == 200 else {}).get("groups", [])
        except Exception as e:
            logger.warning(f"SonarQube groups fetch failed: {e}")
            return result

        devops_groups = [g for g in all_groups if g.get("name", "").startswith("devops-")]

        for group in devops_groups:
            gname = group["name"]
            result["groups"][gname] = {"members": []}

            try:
                resp = await client.get(
                    f"{url}/api/user_groups/users",
                    auth=auth,
                    params={"name": gname, "ps": 100}
                )
                members = (resp.json() if resp.status_code == 200 else {}).get("users", [])
            except Exception:
                members = []

            for m in members:
                login = m.get("login", "")
                result["groups"][gname]["members"].append(login)
                if login not in result["users"]:
                    result["users"][login] = {"display_name": m.get("name", login), "groups": []}
                result["users"][login]["groups"].append(gname)

        # All users
        try:
            resp = await client.get(f"{url}/api/users/search", auth=auth, params={"ps": 100})
            all_users = (resp.json() if resp.status_code == 200 else {}).get("users", [])
            for u in all_users:
                login = u.get("login", "")
                if login and login not in result["users"]:
                    result["users"][login] = {"display_name": u.get("name", login), "groups": []}
        except Exception:
            pass

    return result


async def _sonarqube_grant(creds: dict, username: str, group: str) -> dict:
    url = creds["url"]
    auth = ("admin", creds["password"])
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{url}/api/user_groups/add_user", auth=auth,
            data={"name": group, "login": username}
        )
        if resp.status_code in (200, 204):
            return {"success": True, "message": f"Added to {group}"}
        return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text}"}


async def _sonarqube_revoke(creds: dict, username: str, group: str) -> dict:
    url = creds["url"]
    auth = ("admin", creds["password"])
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{url}/api/user_groups/remove_user", auth=auth,
            data={"name": group, "login": username}
        )
        if resp.status_code in (200, 204):
            return {"success": True, "message": f"Removed from {group}"}
        return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text}"}


# ============================================================
# Nexus
# ============================================================

async def _nexus_get_users_and_groups(creds: dict) -> Dict[str, Any]:
    """Get Nexus users and their devops-* role assignments."""
    url = creds["url"]
    auth = (creds["username"], creds["password"])
    result = {"users": {}, "groups": {}}

    if not creds["password"]:
        return result

    # Pre-populate group structure
    for g in ["devops-readonly", "devops-readwrite", "devops-admin"]:
        result["groups"][g] = {"members": []}

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(f"{url}/service/rest/v1/security/users", auth=auth)
            users = resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.warning(f"Nexus users fetch failed: {e}")
            return result

        for u in users:
            uid = u.get("userId", "")
            roles = u.get("roles", [])
            devops_roles = [r for r in roles if r.startswith("devops-")]

            result["users"][uid] = {
                "display_name": f"{u.get('firstName', '')} {u.get('lastName', '')}".strip() or uid,
                "groups": devops_roles,
            }
            for r in devops_roles:
                if r in result["groups"]:
                    result["groups"][r]["members"].append(uid)

    return result


async def _nexus_grant(creds: dict, username: str, group: str) -> dict:
    """Add a role to a Nexus user."""
    url = creds["url"]
    auth = (creds["username"], creds["password"])

    async with httpx.AsyncClient(timeout=15) as client:
        # Get current user data
        resp = await client.get(f"{url}/service/rest/v1/security/users", auth=auth)
        users = resp.json() if resp.status_code == 200 else []
        user = next((u for u in users if u["userId"] == username), None)
        if not user:
            return {"success": False, "message": f"User '{username}' not found in Nexus"}

        roles = set(user.get("roles", []))
        roles.add(group)
        user["roles"] = list(roles)

        resp = await client.put(
            f"{url}/service/rest/v1/security/users/{username}",
            auth=auth,
            json=user,
            headers={"Content-Type": "application/json"}
        )
        if resp.status_code in (200, 204):
            return {"success": True, "message": f"Role '{group}' added"}
        return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text}"}


async def _nexus_revoke(creds: dict, username: str, group: str) -> dict:
    """Remove a role from a Nexus user."""
    url = creds["url"]
    auth = (creds["username"], creds["password"])

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(f"{url}/service/rest/v1/security/users", auth=auth)
        users = resp.json() if resp.status_code == 200 else []
        user = next((u for u in users if u["userId"] == username), None)
        if not user:
            return {"success": False, "message": f"User '{username}' not found"}

        roles = set(user.get("roles", []))
        roles.discard(group)
        user["roles"] = list(roles)

        resp = await client.put(
            f"{url}/service/rest/v1/security/users/{username}",
            auth=auth,
            json=user,
            headers={"Content-Type": "application/json"}
        )
        if resp.status_code in (200, 204):
            return {"success": True, "message": f"Role '{group}' removed"}
        return {"success": False, "message": f"HTTP {resp.status_code}: {resp.text}"}


# ============================================================
# Jenkins
# ============================================================

async def _jenkins_get_users_and_groups(creds: dict) -> Dict[str, Any]:
    """Get Jenkins users via JSON API (avoids CSRF crumb requirement of scriptText)."""
    url = creds["url"]
    auth = (creds["username"], creds["password"])
    result = {"users": {}, "groups": {}}

    if not creds["password"]:
        return result

    for g in ["devops-readonly", "devops-readwrite", "devops-admin"]:
        result["groups"][g] = {"members": []}

    # Check known users via individual user API
    known_users = ["admin", "svc-devops-backend"]
    async with httpx.AsyncClient(timeout=15) as client:
        for uname in known_users:
            try:
                resp = await client.get(
                    f"{url}/securityRealm/user/{uname}/api/json", auth=auth
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result["users"][uname] = {
                        "display_name": data.get("fullName", uname),
                        "groups": [],
                    }
            except Exception:
                pass

    # Jenkins RBAC is matrix-auth based; map known accounts to groups
    # based on the Groovy init script configuration
    if "admin" in result["users"]:
        result["users"]["admin"]["groups"].append("devops-admin")
        result["groups"]["devops-admin"]["members"].append("admin")
    if "svc-devops-backend" in result["users"]:
        result["users"]["svc-devops-backend"]["groups"].append("devops-readwrite")
        result["groups"]["devops-readwrite"]["members"].append("svc-devops-backend")

    return result


async def _jenkins_grant(creds: dict, username: str, group: str) -> dict:
    """Grant Jenkins permissions via Groovy script (with CSRF crumb)."""
    url = creds["url"]
    auth = (creds["username"], creds["password"])

    perms_map = {
        "devops-readonly": ["Jenkins.READ", "hudson.model.Item.READ", "hudson.model.Item.DISCOVER", "hudson.model.View.READ"],
        "devops-readwrite": ["Jenkins.READ", "hudson.model.Item.BUILD", "hudson.model.Item.READ", "hudson.model.Item.DISCOVER", "hudson.model.Item.WORKSPACE", "hudson.model.Item.CANCEL", "hudson.model.View.READ"],
        "devops-admin": ["Jenkins.ADMINISTER"],
    }
    perms = perms_map.get(group, [])
    if not perms:
        return {"success": False, "message": f"Unknown group: {group}"}

    perm_lines = "\n".join([f'    strategy.add({p}, "{username}")' for p in perms])
    script = f"""
import jenkins.model.*
def instance = Jenkins.getInstance()
def strategy = instance.getAuthorizationStrategy()
if (strategy instanceof hudson.security.GlobalMatrixAuthorizationStrategy ||
    strategy instanceof org.jenkinsci.plugins.matrixauth.GlobalMatrixAuthorizationStrategy) {{
{perm_lines}
    instance.save()
    println("OK")
}} else {{
    println("SKIP: Not using Matrix Authorization - use Jenkins UI to manage permissions")
}}
"""
    async with httpx.AsyncClient(timeout=15) as client:
        # Get CSRF crumb
        try:
            crumb_resp = await client.get(f"{url}/crumbIssuer/api/json", auth=auth)
            crumb_data = crumb_resp.json() if crumb_resp.status_code == 200 else {}
            crumb_header = {crumb_data.get("crumbRequestField", "Jenkins-Crumb"): crumb_data.get("crumb", "")}
        except Exception:
            crumb_header = {}

        resp = await client.post(f"{url}/scriptText", auth=auth, data={"script": script}, headers=crumb_header)
        text = resp.text.strip() if resp.status_code == 200 else ""
        if "OK" in text:
            return {"success": True, "message": f"Permissions granted for {group}"}
        if "SKIP" in text:
            return {"success": False, "message": text}
        return {"success": False, "message": text or f"HTTP {resp.status_code}"}


async def _jenkins_revoke(creds: dict, username: str, group: str) -> dict:
    """Revoking Jenkins Matrix Auth permissions is complex. For safety, return info message."""
    return {
        "success": False,
        "message": "Jenkins Matrix Auth revocation requires manual admin action. "
                   "Use Jenkins UI at /jenkins/configureSecurity/ to modify permissions."
    }


# ============================================================
# Public API
# ============================================================

# Dispatch tables
_FETCH_FUNCS = {
    "gitlab": _gitlab_get_users_and_groups,
    "gitea": _gitea_get_users_and_groups,
    "sonarqube": _sonarqube_get_users_and_groups,
    "nexus": _nexus_get_users_and_groups,
    "jenkins": _jenkins_get_users_and_groups,
}

_GRANT_FUNCS = {
    "gitlab": _gitlab_grant,
    "gitea": _gitea_grant,
    "sonarqube": _sonarqube_grant,
    "nexus": _nexus_grant,
    "jenkins": _jenkins_grant,
}

_REVOKE_FUNCS = {
    "gitlab": _gitlab_revoke,
    "gitea": _gitea_revoke,
    "sonarqube": _sonarqube_revoke,
    "nexus": _nexus_revoke,
    "jenkins": _jenkins_revoke,
}


async def get_overview() -> dict:
    """Get full RBAC overview: all users x all tools with group memberships."""
    creds = _get_admin_creds()

    # Query all tools in parallel
    tasks = {tool: _FETCH_FUNCS[tool](creds[tool]) for tool in TOOLS}
    results = dict(zip(tasks.keys(), await asyncio.gather(*tasks.values(), return_exceptions=True)))

    # Aggregate users across tools
    all_users: Dict[str, dict] = {}

    for tool, data in results.items():
        if isinstance(data, Exception):
            logger.warning(f"RBAC fetch failed for {tool}: {data}")
            continue

        for username, uinfo in data.get("users", {}).items():
            if username not in all_users:
                all_users[username] = {
                    "username": username,
                    "display_name": uinfo.get("display_name", username),
                    "tools": {},
                }
            # Prefer longer display name
            if len(uinfo.get("display_name", "")) > len(all_users[username]["display_name"]):
                all_users[username]["display_name"] = uinfo["display_name"]

            all_users[username]["tools"][tool] = {
                "groups": uinfo.get("groups", []),
                "access_level": _best_group(uinfo.get("groups", [])),
            }

    # Fill in tools with no access
    for user in all_users.values():
        for tool in TOOLS:
            if tool not in user["tools"]:
                user["tools"][tool] = {"groups": [], "access_level": "none"}

    # Summary counts
    readonly_count = sum(1 for u in all_users.values() if _max_access(u) == "devops-readonly")
    readwrite_count = sum(1 for u in all_users.values() if _max_access(u) == "devops-readwrite")
    admin_count = sum(1 for u in all_users.values() if _max_access(u) == "devops-admin")

    return {
        "users": sorted(all_users.values(), key=lambda u: u["username"]),
        "summary": {
            "total_users": len(all_users),
            "readonly": readonly_count,
            "readwrite": readwrite_count,
            "admin": admin_count,
        },
        "tools": TOOLS,
        "available_groups": list(GROUP_LABELS.keys()),
        "group_labels": GROUP_LABELS,
    }


async def get_user_access(username: str) -> dict:
    """Get a single user's access details across all tools."""
    overview = await get_overview()
    for user in overview["users"]:
        if user["username"] == username:
            return {"success": True, "user": user}
    return {"success": False, "message": f"User '{username}' not found"}


async def grant_access(username: str, tool: str, group: str) -> dict:
    """Grant a user access to a group in a specific tool."""
    if tool not in _GRANT_FUNCS:
        return {"success": False, "message": f"Unknown tool: {tool}"}
    if group not in GROUP_LABELS:
        return {"success": False, "message": f"Unknown group: {group}"}

    creds = _get_admin_creds()
    return await _GRANT_FUNCS[tool](creds[tool], username, group)


async def revoke_access(username: str, tool: str, group: str) -> dict:
    """Revoke a user's access from a group in a specific tool."""
    if tool not in _REVOKE_FUNCS:
        return {"success": False, "message": f"Unknown tool: {tool}"}

    creds = _get_admin_creds()
    return await _REVOKE_FUNCS[tool](creds[tool], username, group)


# ============================================================
# Tool Directory - URLs & Credentials
# ============================================================

# Browser-accessible URLs (host port mappings from docker-compose)
TOOL_DIRECTORY = [
    {
        "id": "gitlab",
        "name": "GitLab",
        "icon": "gitlab",
        "color": "#e24329",
        "browser_url": "http://localhost:8929",
        "description": "Source code management, CI/CD pipelines",
        "auth_type": "basic",
        "vault_path": "gitlab",
        "cred_fields": {"username": "username", "password": "password", "token": "token"},
    },
    {
        "id": "gitea",
        "name": "Gitea",
        "icon": "gitea",
        "color": "#609926",
        "browser_url": "http://localhost:3002",
        "description": "Git hosting for Jenkins & GitHub Actions projects",
        "auth_type": "basic",
        "vault_path": "gitea",
        "cred_fields": {"username": "username", "password": "password", "token": "token"},
    },
    {
        "id": "jenkins",
        "name": "Jenkins",
        "icon": "jenkins",
        "color": "#d33833",
        "browser_url": "http://localhost:8080/jenkins/",
        "description": "CI/CD automation server",
        "auth_type": "basic",
        "vault_path": "jenkins",
        "cred_fields": {"username": "username", "password": "password"},
    },
    {
        "id": "sonarqube",
        "name": "SonarQube",
        "icon": "sonarqube",
        "color": "#4e9bcd",
        "browser_url": "http://localhost:9002",
        "description": "Code quality and security analysis",
        "auth_type": "basic",
        "vault_path": "sonarqube",
        "cred_fields": {"password": "password"},
        "static_creds": {"username": "admin"},
    },
    {
        "id": "nexus",
        "name": "Nexus Repository",
        "icon": "nexus",
        "color": "#1ba1c5",
        "browser_url": "http://localhost:8081",
        "description": "Artifact repository and Docker registry",
        "auth_type": "basic",
        "vault_path": "nexus",
        "cred_fields": {"username": "username", "password": "password"},
        "extra_urls": [
            {"label": "Docker Registry", "url": "http://localhost:5001"},
        ],
    },
    {
        "id": "vault",
        "name": "HashiCorp Vault",
        "icon": "vault",
        "color": "#000000",
        "browser_url": "http://localhost:8200",
        "description": "Secret management and encryption",
        "auth_type": "token",
        "vault_path": None,
        "cred_fields": {},
        "static_creds": {"token": "dev-root-token"},
    },
    {
        "id": "chromadb",
        "name": "ChromaDB Admin",
        "icon": "chromadb",
        "color": "#FF6F00",
        "browser_url": "http://localhost:3001",
        "description": "Vector database admin UI",
        "auth_type": "none",
        "vault_path": None,
        "cred_fields": {},
    },
    {
        "id": "grafana",
        "name": "Grafana",
        "icon": "grafana",
        "color": "#F46800",
        "browser_url": "http://localhost:3000",
        "description": "Monitoring dashboards and alerting",
        "auth_type": "basic",
        "vault_path": None,
        "cred_fields": {},
        "static_creds": {"username": "admin", "password": "admin"},
    },
    {
        "id": "prometheus",
        "name": "Prometheus",
        "icon": "prometheus",
        "color": "#E6522C",
        "browser_url": "http://localhost:9090",
        "description": "Metrics collection and querying",
        "auth_type": "none",
        "vault_path": None,
        "cred_fields": {},
    },
    {
        "id": "minio",
        "name": "MinIO",
        "icon": "minio",
        "color": "#C72C48",
        "browser_url": "http://localhost:9001",
        "description": "Object storage (S3-compatible)",
        "auth_type": "basic",
        "vault_path": None,
        "cred_fields": {},
        "static_creds": {"username": "minioadmin", "password": "minioadmin"},
    },
    {
        "id": "splunk",
        "name": "Splunk",
        "icon": "splunk",
        "color": "#65A637",
        "browser_url": "http://localhost:10000",
        "description": "Log aggregation and SIEM",
        "auth_type": "basic",
        "vault_path": "splunk",
        "cred_fields": {"token": "token"},
        "static_creds": {"username": "admin", "password": "Chang3d!"},
    },
    {
        "id": "jaeger",
        "name": "Jaeger",
        "icon": "jaeger",
        "color": "#60D0E4",
        "browser_url": "http://localhost:16686",
        "description": "Distributed tracing",
        "auth_type": "none",
        "vault_path": None,
        "cred_fields": {},
    },
    {
        "id": "cadvisor",
        "name": "cAdvisor",
        "icon": "cadvisor",
        "color": "#2196F3",
        "browser_url": "http://localhost:8082",
        "description": "Container resource monitoring",
        "auth_type": "none",
        "vault_path": None,
        "cred_fields": {},
    },
    {
        "id": "trivy",
        "name": "Trivy Server",
        "icon": "trivy",
        "color": "#1904DA",
        "browser_url": "http://localhost:8083",
        "description": "Container vulnerability scanning",
        "auth_type": "none",
        "vault_path": None,
        "cred_fields": {},
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "icon": "ollama",
        "color": "#000000",
        "browser_url": "http://localhost:11434",
        "description": "Local LLM inference engine",
        "auth_type": "none",
        "vault_path": None,
        "cred_fields": {},
    },
    {
        "id": "jira",
        "name": "Jira",
        "icon": "jira",
        "color": "#0052CC",
        "browser_url": "http://localhost:8180",
        "description": "Project and issue tracking",
        "auth_type": "basic",
        "vault_path": "jira",
        "cred_fields": {"username": "username", "api_token": "api_token"},
    },
    {
        "id": "redmine",
        "name": "Redmine",
        "icon": "redmine",
        "color": "#B32024",
        "browser_url": "http://localhost:8090",
        "description": "Project management and issue tracking",
        "auth_type": "basic",
        "vault_path": None,
        "cred_fields": {},
        "static_creds": {"username": "admin", "password": "admin"},
    },
]


def get_tool_directory() -> list:
    """Return all tools with browser URLs and credentials from Vault."""
    result = []

    for tool in TOOL_DIRECTORY:
        entry = {
            "id": tool["id"],
            "name": tool["name"],
            "icon": tool["icon"],
            "color": tool["color"],
            "browser_url": tool["browser_url"],
            "description": tool["description"],
            "auth_type": tool["auth_type"],
            "credentials": {},
            "extra_urls": tool.get("extra_urls", []),
        }

        # Start with static credentials (preserves declaration order)
        for k, v in tool.get("static_creds", {}).items():
            entry["credentials"][k] = v

        # Overlay/add credentials from Vault (overrides static if same key)
        if tool["vault_path"] and tool["cred_fields"]:
            for display_key, vault_key in tool["cred_fields"].items():
                val = vault.get_secret(tool["vault_path"], vault_key)
                if val:
                    entry["credentials"][display_key] = val

        result.append(entry)

    return result


# ============================================================
# Helpers
# ============================================================

def _best_group(groups: List[str]) -> str:
    """Return the highest access level from a list of groups."""
    priority = {"devops-admin": 3, "devops-readwrite": 2, "devops-readonly": 1}
    best = "none"
    best_p = 0
    for g in groups:
        p = priority.get(g, 0)
        if p > best_p:
            best = g
            best_p = p
    return best


def _max_access(user: dict) -> str:
    """Get user's maximum access level across all tools."""
    all_groups = []
    for tool_data in user.get("tools", {}).values():
        all_groups.extend(tool_data.get("groups", []))
    return _best_group(all_groups)
