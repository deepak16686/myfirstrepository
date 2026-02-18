"""
File: app/config.py
Purpose: Central configuration management -- loads settings from environment variables, .env file,
    and HashiCorp Vault (with fallback priority: service-account creds > admin creds > env vars).
    Also provides ToolsManager for dynamic registration and lookup of DevOps tool connections.
When Used: Imported at application startup (by app/main.py and most routers/services) to access
    the global 'settings' and 'tools_manager' singletons.
Why Created: Consolidates all configuration for 12+ integrated tools (GitLab, Jenkins, SonarQube,
    Nexus, Gitea, Splunk, Jira, Vault, Terraform, Ollama, ChromaDB, Redis, Postgres) into a
    single Pydantic Settings class with Vault secret overlay, avoiding scattered env-var reads.
"""
import os
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from app.integrations.vault_client import vault


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

    # LLM Provider: "ollama", "claude-code", or "openai"
    llm_provider: str = "claude-code"
    claude_model: str = "opus"   # "opus", "sonnet", or "haiku"
    claude_timeout: int = 300      # seconds

    # OpenAI Configuration
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout: int = 300

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

    # Terraform Configuration
    terraform_workspace_dir: str = "/tmp/terraform-workspaces"

    # Terraform Git Server (Gitea - can reuse Jenkins Gitea token)
    terraform_git_url: str = "http://gitea-server:3000"
    terraform_git_token: Optional[str] = None

    # Terraform Cloud Credentials (optional - for live terraform plan/apply)
    # vSphere (On-Prem)
    terraform_vsphere_server: Optional[str] = None
    terraform_vsphere_user: Optional[str] = None
    terraform_vsphere_password: Optional[str] = None

    # Azure
    terraform_azure_subscription_id: Optional[str] = None
    terraform_azure_client_id: Optional[str] = None
    terraform_azure_client_secret: Optional[str] = None
    terraform_azure_tenant_id: Optional[str] = None

    # AWS
    terraform_aws_access_key: Optional[str] = None
    terraform_aws_secret_key: Optional[str] = None
    terraform_aws_region: str = "us-east-1"

    # GCP
    terraform_gcp_project: Optional[str] = None
    terraform_gcp_credentials_file: Optional[str] = None

    # Config file path for additional tools
    tools_config_path: str = "/app/config/tools.json"

    # Vault configuration (read from env vars only, NOT from Vault)
    vault_url: str = "http://vault:8200"
    vault_token: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    def model_post_init(self, __context: Any) -> None:
        """Override settings with Vault secrets when available.

        Priority: service-account creds > admin creds > env vars
        Service accounts are created by rbac-init and stored at secret/service-accounts/{tool}
        Admin creds are seeded by vault-init at secret/{tool} (used as fallback)
        """
        if not vault.is_available:
            return

        # GitLab - prefer service account token
        self.gitlab_token = (
            vault.get_secret("service-accounts/gitlab", "token")
            or vault.get_secret("gitlab", "token")
            or self.gitlab_token
        )

        # Gitea (used as GitHub token) - prefer service account
        self.github_token = (
            vault.get_secret("service-accounts/gitea", "token")
            or vault.get_secret("gitea", "token")
            or self.github_token
        )

        # SonarQube - prefer service account token
        self.sonarqube_token = (
            vault.get_secret("service-accounts/sonarqube", "token")
            or vault.get_secret("sonarqube", "token")
            or self.sonarqube_token
        )
        self.sonarqube_username = (
            vault.get_secret("service-accounts/sonarqube", "username")
            or self.sonarqube_username
        )
        self.sonarqube_password = (
            vault.get_secret("service-accounts/sonarqube", "password")
            or vault.get_secret("sonarqube", "password")
            or self.sonarqube_password
        )

        # Nexus - prefer service account
        self.nexus_username = (
            vault.get_secret("service-accounts/nexus", "username")
            or vault.get_secret("nexus", "username")
            or self.nexus_username
        )
        self.nexus_password = (
            vault.get_secret("service-accounts/nexus", "password")
            or vault.get_secret("nexus", "password")
            or self.nexus_password
        )

        # Jenkins - prefer service account
        self.jenkins_username = (
            vault.get_secret("service-accounts/jenkins", "username")
            or vault.get_secret("jenkins", "username")
            or self.jenkins_username
        )
        self.jenkins_password = (
            vault.get_secret("service-accounts/jenkins", "password")
            or vault.get_secret("jenkins", "password")
            or self.jenkins_password
        )
        self.jenkins_git_token = (
            vault.get_secret("service-accounts/gitea", "token")
            or vault.get_secret("jenkins", "git_token")
            or self.jenkins_git_token
        )

        # Splunk
        self.splunk_token = vault.get_secret("splunk", "token") or self.splunk_token

        # Jira
        self.jira_username = vault.get_secret("jira", "username") or self.jira_username
        self.jira_api_token = vault.get_secret("jira", "api_token") or self.jira_api_token

        # Terraform
        self.terraform_git_token = vault.get_secret("terraform", "git_token") or self.terraform_git_token
        self.terraform_vsphere_server = vault.get_secret("terraform/vsphere", "server") or self.terraform_vsphere_server
        self.terraform_vsphere_user = vault.get_secret("terraform/vsphere", "user") or self.terraform_vsphere_user
        self.terraform_vsphere_password = vault.get_secret("terraform/vsphere", "password") or self.terraform_vsphere_password
        self.terraform_azure_subscription_id = vault.get_secret("terraform/azure", "subscription_id") or self.terraform_azure_subscription_id
        self.terraform_azure_client_id = vault.get_secret("terraform/azure", "client_id") or self.terraform_azure_client_id
        self.terraform_azure_client_secret = vault.get_secret("terraform/azure", "client_secret") or self.terraform_azure_client_secret
        self.terraform_azure_tenant_id = vault.get_secret("terraform/azure", "tenant_id") or self.terraform_azure_tenant_id
        self.terraform_aws_access_key = vault.get_secret("terraform/aws", "access_key") or self.terraform_aws_access_key
        self.terraform_aws_secret_key = vault.get_secret("terraform/aws", "secret_key") or self.terraform_aws_secret_key

        # OpenAI
        self.openai_api_key = vault.get_secret("openai", "api_key") or self.openai_api_key


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
