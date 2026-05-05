"""
Public URL helpers for Docker-hosted tools.

These helpers keep browser-facing URLs consistent across:
- local host ports
- Tailscale path-based access
- custom per-tool domains
"""
from __future__ import annotations

from typing import Dict

from app.config import settings


def _trim(url: str) -> str:
    return (url or "").rstrip("/")


PUBLIC_BASE_URL = _trim(settings.public_base_url)
TAILSCALE_BASE_URL = _trim(settings.tailscale_base_url)
PUBLIC_BASE_DOMAIN = (settings.public_base_domain or "").strip()


_TOOL_PATHS: Dict[str, str] = {
    "gitlab": "/gitlab",
    "gitea": "/gitea",
    "jenkins": "/jenkins",
    "sonarqube": "/sonarqube",
    "nexus": "/nexus",
    "vault": "/vault",
    "chromadb-admin": "/chromadb-admin",
    "grafana": "/grafana",
    "prometheus": "/prometheus",
    "minio": "/minio",
    "splunk": "/splunk",
    "jaeger": "/jaeger",
    "cadvisor": "/cadvisor",
    "trivy": "/trivy",
    "ollama": "/ollama",
    "jira": "/jira",
    "redmine": "/redmine",
    "chromadb": "/chromadb",
    "qdrant": "/qdrant",
    "loki": "/loki",
    "node-exporter": "/node-exporter",
    "devops-api": "/devops-api",
    "chatbot": "/chatbot",
}

_CUSTOM_BASES: Dict[str, str] = {
    "gitlab": f"https://gitlab.{PUBLIC_BASE_DOMAIN}/gitlab" if PUBLIC_BASE_DOMAIN else "",
    "gitea": f"https://gitea.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "jenkins": f"https://jenkins.{PUBLIC_BASE_DOMAIN}/jenkins" if PUBLIC_BASE_DOMAIN else "",
    "sonarqube": f"https://sonarqube.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "nexus": f"https://nexus.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "vault": f"https://vault.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "chromadb-admin": f"https://chromadb-admin.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "grafana": f"https://grafana.{PUBLIC_BASE_DOMAIN}/grafana" if PUBLIC_BASE_DOMAIN else "",
    "prometheus": f"https://prometheus.{PUBLIC_BASE_DOMAIN}/prometheus" if PUBLIC_BASE_DOMAIN else "",
    "minio": f"https://minio.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "splunk": f"https://splunk.{PUBLIC_BASE_DOMAIN}/splunk" if PUBLIC_BASE_DOMAIN else "",
    "jaeger": f"https://jaeger.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "cadvisor": f"https://cadvisor.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "trivy": f"https://trivy.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "ollama": f"https://ollama.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "jira": f"https://jira.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "redmine": f"https://redmine.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "chromadb": f"https://chromadb.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "qdrant": f"https://qdrant.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "loki": f"https://loki.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "node-exporter": f"https://node-exporter.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "devops-api": f"https://devops-api.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
    "chatbot": f"https://chatbot.{PUBLIC_BASE_DOMAIN}" if PUBLIC_BASE_DOMAIN else "",
}

_REPO_BASES = {
    "gitlab": {
        "internal": _trim(settings.gitlab_url),
        "custom": _CUSTOM_BASES["gitlab"],
        "dashboard": f"{PUBLIC_BASE_URL}/gitlab" if PUBLIC_BASE_URL else "",
        "tailscale": f"{TAILSCALE_BASE_URL}/gitlab" if TAILSCALE_BASE_URL else "",
        "local": "http://localhost:8929",
    },
    "gitea": {
        "internal": _trim(settings.github_url),
        "custom": _CUSTOM_BASES["gitea"],
        "dashboard": f"{PUBLIC_BASE_URL}/gitea" if PUBLIC_BASE_URL else "",
        "tailscale": f"{TAILSCALE_BASE_URL}/gitea" if TAILSCALE_BASE_URL else "",
        "local": "http://localhost:3002",
    },
}


def _ensure_slash(url: str) -> str:
    return f"{_trim(url)}/" if url else ""


def get_tool_browser_url(tool_id: str) -> str:
    custom = _CUSTOM_BASES.get(tool_id, "")
    if custom:
        return _ensure_slash(custom)
    path = _TOOL_PATHS.get(tool_id, "")
    return _ensure_slash(f"{PUBLIC_BASE_URL}{path}")


def get_tool_tailscale_url(tool_id: str) -> str:
    path = _TOOL_PATHS.get(tool_id, "")
    return _ensure_slash(f"{TAILSCALE_BASE_URL}{path}")


def get_tool_dashboard_url(tool_id: str) -> str:
    path = _TOOL_PATHS.get(tool_id, "")
    return _ensure_slash(f"{PUBLIC_BASE_URL}{path}")


def to_internal_git_url(url: str) -> str:
    translated = url
    for bases in _REPO_BASES.values():
        internal = bases["internal"]
        for key in ("custom", "dashboard", "tailscale", "local"):
            external = bases.get(key, "")
            if external and translated.startswith(external):
                translated = internal + translated[len(external):]
                break

    translated = translated.replace("http://127.0.0.1:3002", _REPO_BASES["gitea"]["internal"])
    translated = translated.replace("http://127.0.0.1:8929", _REPO_BASES["gitlab"]["internal"])
    translated = translated.replace("https://127.0.0.1:3002", _REPO_BASES["gitea"]["internal"])
    translated = translated.replace("https://127.0.0.1:8929", _REPO_BASES["gitlab"]["internal"])
    return translated


def to_browser_git_url(url: str) -> str:
    translated = url
    for bases in _REPO_BASES.values():
        internal = bases["internal"]
        custom = bases["custom"]
        if internal and custom and translated.startswith(internal):
            translated = custom + translated[len(internal):]
            break

    translated = translated.replace("http://localhost:3002", _REPO_BASES["gitea"]["custom"])
    translated = translated.replace("https://localhost:3002", _REPO_BASES["gitea"]["custom"])
    translated = translated.replace("http://localhost:8929", _REPO_BASES["gitlab"]["custom"])
    translated = translated.replace("https://localhost:8929", _REPO_BASES["gitlab"]["custom"])
    translated = translated.replace("http://127.0.0.1:3002", _REPO_BASES["gitea"]["custom"])
    translated = translated.replace("http://127.0.0.1:8929", _REPO_BASES["gitlab"]["custom"])
    return translated
