"""
Configuration management for DevOps Tools Backend
Supports dynamic tool configuration via environment variables and config file
"""
import os
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


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

    trivy_url: str = "http://trivy-server:8080"

    nexus_url: str = "http://ai-nexus:8081"
    nexus_username: str = "admin"
    nexus_password: Optional[str] = None

    # GitHub/Gitea Configuration (Gitea for free self-hosted GitHub Actions alternative)
    github_url: str = "http://gitea-server:3000"  # Gitea server URL
    github_token: Optional[str] = None  # Personal access token

    chromadb_url: str = "http://chromadb:8000"

    ollama_url: str = "http://ollama:11434"

    # LLM Provider: "ollama" or "claude-code"
    llm_provider: str = "claude-code"
    claude_model: str = "opus"   # "opus", "sonnet", or "haiku"
    claude_timeout: int = 300      # seconds

    redis_url: str = "redis://redis:6379/0"

    postgres_url: str = "postgresql://modernization:modernization123@postgres:5432/legacy_modernization"

    # Jira Configuration
    jira_url: str = "http://jira:8080"
    jira_username: Optional[str] = None
    jira_api_token: Optional[str] = None
    jira_project_key: str = "DEVOPS"

    # Splunk Configuration (HEC uses HTTPS)
    splunk_url: str = "https://ai-splunk:8088"
    splunk_token: Optional[str] = None

    # Jenkins Configuration
    jenkins_url: str = "http://jenkins-master:8080/jenkins"
    jenkins_username: Optional[str] = None
    jenkins_password: Optional[str] = None

    # Jenkins Git Server (Gitea - separate from GitLab to avoid dual CI trigger)
    jenkins_git_url: str = "http://gitea-server:3000"
    jenkins_git_token: Optional[str] = None

    # Config file path for additional tools
    tools_config_path: str = "/app/config/tools.json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


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
            ),
            "github": ToolConfig(
                base_url=self.settings.github_url,
                token=self.settings.github_token,
                enabled=bool(self.settings.github_token)
            ),
            "jira": ToolConfig(
                base_url=self.settings.jira_url,
                username=self.settings.jira_username,
                api_key=self.settings.jira_api_token,
                password=self.settings.jira_api_token,
                enabled=bool(self.settings.jira_username and self.settings.jira_api_token)
            ),
            "splunk": ToolConfig(
                base_url=self.settings.splunk_url,
                token=self.settings.splunk_token,
                enabled=True
            ),
            "jenkins": ToolConfig(
                base_url=self.settings.jenkins_url,
                username=self.settings.jenkins_username,
                password=self.settings.jenkins_password,
                enabled=True
            ),
            "redis": ToolConfig(
                base_url=self.settings.redis_url,
                enabled=True
            ),
            "postgres": ToolConfig(
                base_url=self.settings.postgres_url,
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
