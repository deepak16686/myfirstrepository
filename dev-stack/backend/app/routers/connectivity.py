"""
Connectivity Router - Check connectivity to all DevOps tools
"""
import asyncio
import time
import socket
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional
from fastapi import APIRouter, HTTPException

from app.config import settings, tools_manager, ToolConfig
from app.models.schemas import (
    ToolStatus, ConnectivityResult, ConnectivityReport,
    AccessRequest, AccessRequestResponse, AccessGroup
)
from app.integrations.gitlab import GitLabIntegration
from app.integrations.sonarqube import SonarQubeIntegration
from app.integrations.trivy import TrivyIntegration
from app.integrations.nexus import NexusIntegration
from app.integrations.ollama import OllamaIntegration
from app.integrations.chromadb import ChromaDBIntegration
from app.integrations.jira import JiraIntegration
from app.integrations.splunk import SplunkIntegration
from app.integrations.jenkins import JenkinsIntegration
from app.integrations.github import GitHubIntegration

router = APIRouter(prefix="/connectivity", tags=["Tool Connectivity"])

# Tool display metadata with access groups/roles
TOOL_DISPLAY = {
    "gitlab": {
        "display_name": "GitLab",
        "icon": "gitlab",
        "auth_type": "Token",
        "access_groups": [
            {"name": "Guest", "description": "View projects and leave comments"},
            {"name": "Reporter", "description": "View code, pull/clone repos"},
            {"name": "Developer", "description": "Push code, create merge requests"},
            {"name": "Maintainer", "description": "Manage branches, approve MRs, CI/CD settings"},
            {"name": "Owner", "description": "Full administrative access"},
        ],
    },
    "sonarqube": {
        "display_name": "SonarQube",
        "icon": "shield-check",
        "auth_type": "Token/Basic",
        "access_groups": [
            {"name": "sonar-users", "description": "Browse projects and view analysis results"},
            {"name": "sonar-developers", "description": "Run scans and manage quality profiles"},
            {"name": "sonar-administrators", "description": "Full admin: manage projects, rules, and users"},
        ],
    },
    "trivy": {
        "display_name": "Trivy",
        "icon": "shield-alert",
        "auth_type": "None",
        "access_groups": [
            {"name": "scanner", "description": "Run vulnerability scans on images"},
        ],
    },
    "nexus": {
        "display_name": "Nexus Repository",
        "icon": "package",
        "auth_type": "Basic",
        "access_groups": [
            {"name": "nx-readonly", "description": "Browse and download artifacts"},
            {"name": "nx-deploy", "description": "Upload and deploy artifacts to repositories"},
            {"name": "nx-admin", "description": "Full admin: manage repos, users, and settings"},
        ],
    },
    "chromadb": {
        "display_name": "ChromaDB",
        "icon": "database",
        "auth_type": "None",
        "access_groups": [
            {"name": "reader", "description": "Query collections and embeddings"},
            {"name": "writer", "description": "Create collections and insert data"},
        ],
    },
    "ollama": {
        "display_name": "Ollama LLM",
        "icon": "brain",
        "auth_type": "None",
        "access_groups": [
            {"name": "user", "description": "Run inference and chat with models"},
            {"name": "model-admin", "description": "Create, pull, and delete models"},
        ],
    },
    "github": {
        "display_name": "Gitea/GitHub",
        "icon": "github",
        "auth_type": "Token",
        "access_groups": [
            {"name": "Read", "description": "Clone repos and view issues"},
            {"name": "Write", "description": "Push code and manage issues/PRs"},
            {"name": "Admin", "description": "Full repo and org administration"},
        ],
    },
    "jira": {
        "display_name": "Jira",
        "icon": "ticket",
        "auth_type": "Basic/API Token",
        "access_groups": [
            {"name": "jira-software-users", "description": "Create and manage issues in projects"},
            {"name": "jira-administrators", "description": "Full admin: manage projects, workflows, users"},
        ],
    },
    "splunk": {
        "display_name": "Splunk",
        "icon": "activity",
        "auth_type": "HEC Token",
        "access_groups": [
            {"name": "user", "description": "Search and view dashboards"},
            {"name": "power", "description": "Create reports, alerts, and dashboards"},
            {"name": "sc_admin", "description": "Full admin: manage indexes, inputs, and users"},
        ],
    },
    "jenkins": {
        "display_name": "Jenkins",
        "icon": "settings",
        "auth_type": "Basic",
        "access_groups": [
            {"name": "viewer", "description": "View jobs and build logs"},
            {"name": "developer", "description": "Trigger builds and manage job configurations"},
            {"name": "admin", "description": "Full admin: manage nodes, plugins, and security"},
        ],
    },
    "redis": {
        "display_name": "Redis",
        "icon": "database",
        "auth_type": "None",
        "access_groups": [
            {"name": "readonly", "description": "Read-only access to cache data"},
            {"name": "readwrite", "description": "Read and write cache data"},
        ],
    },
    "postgres": {
        "display_name": "PostgreSQL",
        "icon": "database",
        "auth_type": "Connection String",
        "access_groups": [
            {"name": "pg_read", "description": "SELECT access on database tables"},
            {"name": "pg_write", "description": "INSERT, UPDATE, DELETE on database tables"},
            {"name": "pg_admin", "description": "Full database admin with DDL privileges"},
        ],
    },
}

# Integration class map (HTTP-based tools only)
INTEGRATION_MAP = {
    "gitlab": GitLabIntegration,
    "sonarqube": SonarQubeIntegration,
    "trivy": TrivyIntegration,
    "nexus": NexusIntegration,
    "ollama": OllamaIntegration,
    "chromadb": ChromaDBIntegration,
    "jira": JiraIntegration,
    "splunk": SplunkIntegration,
    "jenkins": JenkinsIntegration,
    "github": GitHubIntegration,
}


async def _check_tcp_connectivity(url: str) -> tuple:
    """Check TCP connectivity for non-HTTP services like Redis/PostgreSQL"""
    start = time.time()
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port
        if not port:
            if parsed.scheme == "redis":
                port = 6379
            elif parsed.scheme in ("postgresql", "postgres"):
                port = 5432
            else:
                port = 80

        loop = asyncio.get_event_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        await loop.run_in_executor(None, sock.connect, (host, port))
        sock.close()
        latency = (time.time() - start) * 1000
        return ToolStatus.HEALTHY, latency, None
    except Exception as e:
        latency = (time.time() - start) * 1000
        return ToolStatus.UNHEALTHY, latency, str(e)


async def _check_tool(tool_name: str, config: ToolConfig) -> ConnectivityResult:
    """Check connectivity for a single tool"""
    display = TOOL_DISPLAY.get(tool_name, {
        "display_name": tool_name.title(),
        "icon": "tool",
        "auth_type": "Unknown",
        "access_groups": [],
    })
    groups = [AccessGroup(**g) for g in display.get("access_groups", [])]

    # TCP-only checks for non-HTTP services
    if tool_name in ("redis", "postgres"):
        status, latency, error = await _check_tcp_connectivity(config.base_url)
        return ConnectivityResult(
            name=tool_name,
            display_name=display["display_name"],
            icon=display["icon"],
            status=status,
            version=None,
            latency_ms=round(latency, 1),
            auth_type=display["auth_type"],
            base_url=config.base_url,
            error=error,
            access_groups=groups,
        )

    # HTTP-based tools
    integration_class = INTEGRATION_MAP.get(tool_name)
    if not integration_class:
        return ConnectivityResult(
            name=tool_name,
            display_name=display["display_name"],
            icon=display["icon"],
            status=ToolStatus.UNKNOWN,
            base_url=config.base_url,
            auth_type=display["auth_type"],
            error="No integration available",
            access_groups=groups,
        )

    start = time.time()
    try:
        integration = integration_class(config)
        status = await integration.health_check()
        version = await integration.get_version()
        await integration.close()
        latency = (time.time() - start) * 1000
        return ConnectivityResult(
            name=tool_name,
            display_name=display["display_name"],
            icon=display["icon"],
            status=status,
            version=version,
            latency_ms=round(latency, 1),
            auth_type=display["auth_type"],
            base_url=config.base_url,
            error=None,
            access_groups=groups,
        )
    except Exception as e:
        latency = (time.time() - start) * 1000
        return ConnectivityResult(
            name=tool_name,
            display_name=display["display_name"],
            icon=display["icon"],
            status=ToolStatus.UNHEALTHY,
            latency_ms=round(latency, 1),
            auth_type=display["auth_type"],
            base_url=config.base_url,
            error=str(e),
            access_groups=groups,
        )


@router.get("/", response_model=ConnectivityReport)
async def check_all_connectivity():
    """Check connectivity to all configured tools concurrently"""
    tasks = []
    for name, config in tools_manager.list_tools().items():
        tasks.append(_check_tool(name, config))

    results = await asyncio.gather(*tasks)

    healthy = sum(1 for r in results if r.status == ToolStatus.HEALTHY)
    unhealthy = sum(1 for r in results if r.status == ToolStatus.UNHEALTHY)
    unknown = sum(1 for r in results if r.status == ToolStatus.UNKNOWN)

    return ConnectivityReport(
        timestamp=datetime.now().isoformat(),
        total=len(results),
        healthy=healthy,
        unhealthy=unhealthy,
        unknown=unknown,
        tools=list(results)
    )


@router.get("/{tool_name}", response_model=ConnectivityResult)
async def check_tool_connectivity(tool_name: str):
    """Check connectivity to a specific tool"""
    config = tools_manager.get_tool(tool_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not configured")
    return await _check_tool(tool_name, config)


@router.post("/access-request", response_model=AccessRequestResponse)
async def request_tool_access(request: AccessRequest):
    """Submit an access request for tools via Jira"""
    jira_config = tools_manager.get_tool("jira")
    if not jira_config or not jira_config.enabled:
        return AccessRequestResponse(
            success=False,
            message="Jira is not configured. Please configure Jira to submit access requests."
        )

    try:
        jira = JiraIntegration(jira_config)
        tool_names = [t.tool for t in request.tools]
        tools_list = ", ".join(tool_names)
        summary = f"Tool Access Request: {tools_list}"

        # Build detailed tools section with requested groups
        tools_section = ""
        for t in request.tools:
            display = TOOL_DISPLAY.get(t.tool, {})
            display_name = display.get("display_name", t.tool)
            if t.groups:
                groups_str = ", ".join(t.groups)
                tools_section += f"- *{display_name}*: {groups_str}\n"
            else:
                tools_section += f"- *{display_name}*\n"

        description = (
            f"*Requester:* {request.requester_name} ({request.requester_email})\n\n"
            f"*Tools & Requested Access Groups:*\n"
            + tools_section +
            f"\n*Reason:*\n{request.reason}\n\n"
            f"_Submitted via DevOps Platform Connectivity Validator_"
        )

        result = await jira.create_issue(
            project_key=settings.jira_project_key,
            summary=summary,
            description=description,
            issue_type="Task",
            labels=["access-request", "devops-platform"]
        )
        await jira.close()

        issue_key = result.get("key", "")
        issue_url = f"{jira_config.base_url}/browse/{issue_key}" if issue_key else None

        return AccessRequestResponse(
            success=True,
            jira_issue_key=issue_key,
            jira_issue_url=issue_url,
            message=f"Access request {issue_key} created successfully"
        )
    except Exception as e:
        return AccessRequestResponse(
            success=False,
            message=f"Failed to create Jira ticket: {str(e)}"
        )
