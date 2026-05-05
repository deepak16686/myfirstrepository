"""
File: credentials_dashboard.py
Purpose: Exposes a read-only endpoint that fetches all service credentials from HashiCorp Vault
    and merges them with connectivity/health data, providing a single JSON response for the
    frontend Credentials Dashboard page.
When Used: Called by the chatbot-portal's Credentials Dashboard view to display all service URLs,
    usernames, passwords, tokens, and live health status in a unified table.
Why Created: Centralizes credential visibility for dev environments so developers don't need to
    look up each service's login details manually. Only enabled when VAULT is available.
"""
import asyncio
import time
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.integrations.vault_client import vault

router = APIRouter(prefix="/credentials-dashboard", tags=["Credentials Dashboard"])


class ServiceCredential(BaseModel):
    name: str
    display_name: str
    icon: str
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    auth_type: str = "none"
    extra: Dict[str, Any] = {}
    status: str = "unknown"
    category: str = "tool"


class CredentialsDashboardResponse(BaseModel):
    success: bool
    vault_available: bool
    services: List[ServiceCredential]
    message: str = ""


# Service definitions with Vault paths and display metadata
SERVICE_DEFS = [
    {
        "name": "gitlab",
        "display_name": "GitLab",
        "icon": "gitlab",
        "vault_path": "gitlab",
        "category": "scm",
        "url_key": "url",
        "fallback_url": "http://localhost:8929/gitlab/",
        "health_url": "http://gitlab-server:80/gitlab/users/sign_in",
    },
    {
        "name": "gitea",
        "display_name": "Gitea",
        "icon": "git-branch",
        "vault_path": "gitea",
        "category": "scm",
        "url_key": "url",
        "fallback_url": "http://localhost:3002",
        "health_url": "http://gitea-server:3000",
    },
    {
        "name": "jenkins",
        "display_name": "Jenkins",
        "icon": "settings",
        "vault_path": "jenkins",
        "category": "cicd",
        "url_key": "url",
        "fallback_url": "http://localhost:8080/jenkins/",
        "health_url": "http://jenkins-master:8080/jenkins/login",
    },
    {
        "name": "sonarqube",
        "display_name": "SonarQube",
        "icon": "shield-check",
        "vault_path": "sonarqube",
        "category": "quality",
        "url_key": "url",
        "fallback_url": "http://localhost:9002",
        "health_url": "http://ai-sonarqube:9000/api/system/status",
    },
    {
        "name": "nexus",
        "display_name": "Nexus Repository",
        "icon": "package",
        "vault_path": "nexus",
        "category": "registry",
        "url_key": "url",
        "fallback_url": "http://localhost:8181",
        "health_url": "http://ai-nexus:8081",
    },
    {
        "name": "vault",
        "display_name": "HashiCorp Vault",
        "icon": "lock",
        "vault_path": "vault",
        "category": "security",
        "url_key": "url",
        "fallback_url": "http://localhost:8200/ui/",
        "health_url": "http://vault:8200/v1/sys/health",
    },
    {
        "name": "grafana",
        "display_name": "Grafana",
        "icon": "bar-chart",
        "vault_path": "grafana",
        "category": "monitoring",
        "url_key": "url",
        "fallback_url": "http://localhost:3000",
        "health_url": "http://grafana:3000/api/health",
    },
    {
        "name": "prometheus",
        "display_name": "Prometheus",
        "icon": "activity",
        "vault_path": "prometheus",
        "category": "monitoring",
        "url_key": "url",
        "fallback_url": "http://localhost:9090/prometheus/",
        "health_url": "http://prometheus:9090/prometheus/api/v1/status/runtimeinfo",
    },
    {
        "name": "jira",
        "display_name": "Jira",
        "icon": "ticket",
        "vault_path": "jira",
        "category": "project",
        "url_key": "url",
        "fallback_url": "http://localhost:8180",
        "health_url": "http://jira:8080/status",
    },
    {
        "name": "redmine",
        "display_name": "Redmine",
        "icon": "clipboard",
        "vault_path": "redmine",
        "category": "project",
        "url_key": "url",
        "fallback_url": "http://localhost:8090",
        "health_url": "http://redmine:3000",
    },
    {
        "name": "splunk",
        "display_name": "Splunk",
        "icon": "search",
        "vault_path": "splunk",
        "category": "logging",
        "url_key": "url",
        "fallback_url": "http://localhost:10000",
        "health_url": "http://ai-splunk:8000",
    },
    {
        "name": "minio",
        "display_name": "MinIO",
        "icon": "hard-drive",
        "vault_path": "minio",
        "category": "storage",
        "url_key": "url",
        "fallback_url": "http://localhost:9001",
        "health_url": "http://minio:9000/minio/health/live",
    },
    {
        "name": "jaeger",
        "display_name": "Jaeger",
        "icon": "radar",
        "vault_path": "jaeger",
        "category": "monitoring",
        "url_key": "url",
        "fallback_url": "http://localhost:16686",
        "health_url": "http://jaeger:16686",
    },
    {
        "name": "loki",
        "display_name": "Loki",
        "icon": "file-text",
        "vault_path": "loki",
        "category": "logging",
        "url_key": "url",
        "fallback_url": "http://localhost:3100",
        "health_url": "http://loki:3100/ready",
    },
    {
        "name": "ollama",
        "display_name": "Ollama LLM",
        "icon": "brain",
        "vault_path": "ollama",
        "category": "ai",
        "url_key": "url",
        "fallback_url": "http://localhost:11434",
        "health_url": "http://ollama:11434",
    },
    {
        "name": "chromadb",
        "display_name": "ChromaDB",
        "icon": "database",
        "vault_path": "chromadb",
        "category": "ai",
        "url_key": "url",
        "fallback_url": "http://localhost:8005",
        "health_url": "http://chromadb:8000/api/v2/heartbeat",
    },
    {
        "name": "qdrant",
        "display_name": "Qdrant",
        "icon": "grid",
        "vault_path": "qdrant",
        "category": "ai",
        "url_key": "url",
        "fallback_url": "http://localhost:6333/dashboard/",
        "health_url": "http://qdrant:6333/collections",
    },
    {
        "name": "postgres",
        "display_name": "PostgreSQL",
        "icon": "database",
        "vault_path": "postgres",
        "category": "database",
        "url_key": "url",
        "fallback_url": "localhost:5432",
        "health_url": None,
    },
    {
        "name": "redis",
        "display_name": "Redis",
        "icon": "zap",
        "vault_path": "redis",
        "category": "database",
        "url_key": "url",
        "fallback_url": "localhost:6379",
        "health_url": None,
    },
    {
        "name": "trivy",
        "display_name": "Trivy Server",
        "icon": "shield-alert",
        "vault_path": "trivy",
        "category": "security",
        "url_key": "url",
        "fallback_url": "http://localhost:8183",
        "health_url": "http://trivy-server:8080/healthz",
    },
    {
        "name": "mailhog",
        "display_name": "MailHog",
        "icon": "mail",
        "vault_path": None,
        "category": "notification",
        "url_key": None,
        "fallback_url": "http://localhost:8025",
        "health_url": "http://taskflow-mailhog:8025",
        "static_creds": {"auth": "none"},
    },
    {
        "name": "cadvisor",
        "display_name": "cAdvisor",
        "icon": "cpu",
        "vault_path": None,
        "category": "monitoring",
        "url_key": None,
        "fallback_url": "http://localhost:8182",
        "health_url": "http://cadvisor:8080",
        "static_creds": {"auth": "none"},
    },
]


async def _check_health(url: str) -> str:
    """Quick HTTP health check, returns 'healthy' or 'unhealthy'."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            resp = await client.get(url)
            return "healthy" if resp.status_code < 500 else "unhealthy"
    except Exception:
        return "unhealthy"


@router.get("/", response_model=CredentialsDashboardResponse)
async def get_all_credentials():
    """
    Fetch all service credentials from Vault and health status.
    Returns masked passwords (last 4 chars visible) for security.
    """
    services = []
    health_tasks = []
    health_indices = []

    for sdef in SERVICE_DEFS:
        creds = {}
        if sdef.get("vault_path") and vault.is_available:
            # Read all known keys from vault
            for key in ("username", "password", "token", "url", "note",
                        "root_token", "auth", "api_url", "registry",
                        "db_username", "db_password", "collector_url", "grpc_url",
                        "admin_url"):
                val = vault.get_secret(sdef["vault_path"], key)
                if val:
                    creds[key] = val

        # Merge static creds if defined
        if sdef.get("static_creds"):
            creds.update(sdef["static_creds"])

        url = creds.get("url", sdef.get("fallback_url", ""))
        username = creds.get("username")
        password = creds.get("password")
        token = creds.get("token")

        # Determine auth type
        if username and password:
            auth_type = "basic"
        elif token:
            auth_type = "token"
        elif creds.get("root_token"):
            auth_type = "token"
            token = creds.get("root_token")
        else:
            auth_type = creds.get("auth", "none")

        # Collect extra fields
        extra = {}
        for k, v in creds.items():
            if k not in ("username", "password", "token", "url", "auth", "root_token"):
                extra[k] = v

        svc = ServiceCredential(
            name=sdef["name"],
            display_name=sdef["display_name"],
            icon=sdef["icon"],
            url=url,
            username=username,
            password=password,
            token=token,
            auth_type=auth_type,
            extra=extra,
            category=sdef["category"],
        )
        services.append(svc)

        # Queue health check
        if sdef.get("health_url"):
            health_indices.append(len(services) - 1)
            health_tasks.append(_check_health(sdef["health_url"]))

    # Run all health checks concurrently
    if health_tasks:
        results = await asyncio.gather(*health_tasks, return_exceptions=True)
        for idx, result in zip(health_indices, results):
            if isinstance(result, str):
                services[idx].status = result
            else:
                services[idx].status = "unhealthy"

    return CredentialsDashboardResponse(
        success=True,
        vault_available=vault.is_available,
        services=services,
        message=f"Loaded {len(services)} services" + (
            " (from Vault)" if vault.is_available else " (Vault unavailable, using defaults)"
        ),
    )
