"""
Configuration management for DevOps Tools Backend
Supports dynamic tool configuration via environment variables and config file
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings


# Repository layout anchors
_APP_DIR = Path(__file__).resolve().parent          # .../devops-tools-backend/app
_PROJECT_ROOT = _APP_DIR.parent                     # .../devops-tools-backend
_DEFAULT_REGISTRY_PATH = _PROJECT_ROOT / "config" / "tools.yaml"


class ToolConfig(BaseModel):
    """Configuration for a single tool"""
    enabled: bool = True
    base_url: str
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class Settings(BaseSettings):
    """Application settings"""
    app_name: str = "DevOps Tools Backend"
    app_version: str = "1.0.0"
    debug: bool = False

    # API Settings
    api_prefix: str = "/api/v1"
    cors_origins: list = ["*"]

    # Tool configurations - loaded from environment or config file
    # Use container names for Docker network communication
    gitlab_url: str = "http://gitlab-server"
    gitlab_token: Optional[str] = None

    sonarqube_url: str = "http://sonarqube:9000"
    sonarqube_token: Optional[str] = None
    sonarqube_username: str = "admin"
    sonarqube_password: Optional[str] = None

    trivy_url: str = "http://trivy:8083"

    nexus_url: str = "http://ai-nexus:8081"
    nexus_username: str = "admin"
    nexus_password: Optional[str] = None

    chromadb_url: str = "http://chromadb:8000"

    ollama_url: str = "http://ollama:11434"

    redis_url: str = "redis://redis:6379/0"

    # Postgres DSN must be provided via env (POSTGRES_URL) or config file.
    # No credential default is shipped in source.
    postgres_url: Optional[str] = None

    # Config file path for additional tools
    tools_config_path: str = "/app/config/tools.json"

    # ------------------------------------------------------------------
    # Portal registry + health prober settings
    # ------------------------------------------------------------------
    # Path to the canonical YAML tool registry consumed by /api/v1/portal/*.
    # Can be absolute or relative; relative resolves against repo root.
    tools_registry_path: Path = _DEFAULT_REGISTRY_PATH

    # How often the background task re-probes every tool.
    health_probe_interval_seconds: int = 30
    # Per-request timeout for a single HTTP probe.
    health_probe_timeout_seconds: float = 4.0
    # TTL written on each portal:health:* Redis key.
    health_cache_ttl_seconds: int = 60

    # Optional explicit path to the `tailscale` CLI. When None, we look up
    # via PATH at call time.
    tailscale_cli_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Vault-backed credentials endpoint (GET /portal/tools/{id}/credentials)
    # ------------------------------------------------------------------
    # Base URL of the Vault server (e.g. "http://vault:8200" inside the
    # compose network, or "http://localhost:8200" from the host). Empty
    # disables the credentials endpoint → 503.
    vault_addr: str = Field(default="", description="Vault address, e.g. http://vault:8200")
    # Token used by the backend to read KV v2 secrets. NEVER surfaced in
    # logs, responses, or settings.dict() output — we exclude it from repr
    # via pydantic Field(repr=False) so accidental `print(settings)` never
    # leaks it.
    vault_token: str = Field(default="", repr=False, description="Vault token (never logged)")
    # Per-request HTTP timeout for Vault reads.
    vault_timeout_seconds: float = 3.0

    # Header clients must present to fetch credentials. The *name* is
    # configurable mostly so ingress / proxy middleware can distinguish it.
    portal_operator_header: str = "X-Portal-Operator"
    # Exact-value token that clients send in `portal_operator_header`.
    # Empty disables the credentials endpoint entirely (→ 503).
    portal_operator_token: str = Field(
        default="",
        repr=False,
        description="Operator token compared with hmac.compare_digest; empty disables endpoint",
    )

    @field_validator("tools_registry_path", mode="after")
    @classmethod
    def _resolve_registry_path(cls, v: Path) -> Path:
        """Resolve relative paths against the repo root so the backend can be
        started from any CWD without losing its config."""
        p = Path(v)
        if not p.is_absolute():
            p = (_PROJECT_ROOT / p).resolve()
        return p

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class ToolsManager:
    """Manages dynamic tool configurations"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._tools: Dict[str, ToolConfig] = {}
        self._load_default_tools()
        self._load_config_file()

    def _load_default_tools(self):
        """Load default tool configurations from settings"""
        self._tools = {
            "gitlab": ToolConfig(
                base_url=self.settings.gitlab_url,
                token=self.settings.gitlab_token,
                enabled=bool(self.settings.gitlab_token)
            ),
            "sonarqube": ToolConfig(
                base_url=self.settings.sonarqube_url,
                token=self.settings.sonarqube_token,
                username=self.settings.sonarqube_username,
                password=self.settings.sonarqube_password,
                enabled=bool(self.settings.sonarqube_token or self.settings.sonarqube_password)
            ),
            "trivy": ToolConfig(
                base_url=self.settings.trivy_url,
                enabled=True
            ),
            "nexus": ToolConfig(
                base_url=self.settings.nexus_url,
                username=self.settings.nexus_username,
                password=self.settings.nexus_password,
                enabled=bool(self.settings.nexus_password)
            ),
            "chromadb": ToolConfig(
                base_url=self.settings.chromadb_url,
                enabled=True
            ),
            "ollama": ToolConfig(
                base_url=self.settings.ollama_url,
                enabled=True
            )
        }

    def _load_config_file(self):
        """Load additional tools from config file"""
        config_path = self.settings.tools_config_path
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    for name, tool_config in config.get("tools", {}).items():
                        self._tools[name] = ToolConfig(**tool_config)
            except Exception as e:
                print(f"Error loading tools config: {e}")

    def get_tool(self, name: str) -> Optional[ToolConfig]:
        """Get configuration for a specific tool"""
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, ToolConfig]:
        """List all configured tools"""
        return self._tools

    def add_tool(self, name: str, config: ToolConfig):
        """Add or update a tool configuration"""
        self._tools[name] = config

    def remove_tool(self, name: str) -> bool:
        """Remove a tool configuration"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def save_config(self):
        """Save current tool configurations to file"""
        config_path = self.settings.tools_config_path
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        config = {
            "tools": {name: tool.model_dump() for name, tool in self._tools.items()}
        }
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)


# Global instances
settings = Settings()
tools_manager = ToolsManager(settings)
