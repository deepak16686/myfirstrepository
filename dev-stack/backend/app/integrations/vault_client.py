"""
File: vault_client.py
Purpose: HashiCorp Vault KV-v2 secret client implemented as a singleton. Resolves the root token from
         either VAULT_TOKEN env var or the persistent file at /vault/file/.root-token. Supports both
         token auth (dev/admin) and AppRole auth (VAULT_ROLE_ID + VAULT_SECRET_ID for service accounts).
         Falls back gracefully to environment variables if Vault is unavailable.
When Used: Called by config.py at startup to overlay Vault secrets onto Settings fields (GitLab PAT,
           Gitea token, SonarQube token, Nexus password, etc.). The secret resolution priority chain
           is: service-accounts path > admin path > environment variables.
Why Created: Centralizes all secret management through Vault so credentials are never stored in .env
             files or docker-compose environment variables in production. The fallback mechanism
             ensures the backend still starts even if Vault is temporarily unavailable.
"""
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class VaultSecretResolver:
    """Resolves secrets from HashiCorp Vault KV-v2."""

    # Path where vault-init stores the root token (persistent mode)
    TOKEN_FILE = "/vault/file/.root-token"

    def __init__(self):
        self.vault_url = os.environ.get("VAULT_URL", "http://vault:8200")
        self.vault_token = self._resolve_token()
        self._vault_role_id = os.environ.get("VAULT_ROLE_ID", "")
        self._vault_secret_id = os.environ.get("VAULT_SECRET_ID", "")
        self._client = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._available = False
        self._auth_method = None
        self._connect()

    def _resolve_token(self) -> str:
        """Resolve Vault token: env var first, then token file (persistent mode)."""
        env_token = os.environ.get("VAULT_TOKEN", "")
        if env_token:
            return env_token
        # Try reading from the shared vault-data volume (written by vault-init)
        if os.path.isfile(self.TOKEN_FILE):
            try:
                token = open(self.TOKEN_FILE).read().strip()
                if token:
                    logger.info(f"Vault token loaded from {self.TOKEN_FILE}")
                    return token
            except Exception as e:
                logger.warning(f"Could not read {self.TOKEN_FILE}: {e}")
        return ""

    def _connect(self):
        """Attempt to connect to Vault via AppRole or token."""
        try:
            import hvac
        except ImportError:
            logger.warning("hvac not installed -- Vault disabled")
            return

        # Try AppRole auth first (service account), then token auth
        if self._vault_role_id and self._vault_secret_id:
            self._connect_approle(hvac)
        elif self.vault_token:
            self._connect_token(hvac)
        else:
            logger.info("No Vault credentials set -- Vault disabled, using env vars")

    def _connect_approle(self, hvac):
        """Connect using AppRole authentication (preferred for service accounts)."""
        try:
            self._client = hvac.Client(url=self.vault_url)
            result = self._client.auth.approle.login(
                role_id=self._vault_role_id,
                secret_id=self._vault_secret_id
            )
            self._client.token = result['auth']['client_token']
            if self._client.is_authenticated():
                self._available = True
                self._auth_method = "approle"
                logger.info(f"Vault connected at {self.vault_url} (AppRole auth)")
            else:
                logger.warning("Vault AppRole login failed -- trying token auth")
                self._client = None
                if self.vault_token:
                    self._connect_token(hvac)
        except Exception as e:
            logger.warning(f"Vault AppRole auth failed ({e}) -- trying token auth")
            self._client = None
            if self.vault_token:
                self._connect_token(hvac)

    def _connect_token(self, hvac):
        """Connect using static token authentication (dev/admin mode)."""
        try:
            self._client = hvac.Client(url=self.vault_url, token=self.vault_token)
            if self._client.is_authenticated():
                self._available = True
                self._auth_method = "token"
                logger.info(f"Vault connected at {self.vault_url} (token auth)")
            else:
                logger.warning("Vault token is invalid -- falling back to env vars")
                self._client = None
        except Exception as e:
            logger.warning(f"Vault unavailable ({e}) -- falling back to env vars")
            self._client = None

    def get_secret(self, path: str, key: str) -> Optional[str]:
        """
        Read a single key from Vault KV-v2.

        path: e.g. "service-accounts/gitlab", "gitlab", "jenkins"
        key:  e.g. "token", "password", "username"

        Returns None if Vault is unavailable or key doesn't exist.
        """
        if not self._available:
            return None

        if path not in self._cache:
            try:
                response = self._client.secrets.kv.v2.read_secret_version(
                    path=path, mount_point="secret"
                )
                self._cache[path] = response["data"]["data"]
            except Exception as e:
                logger.debug(f"Vault read failed for secret/{path}: {e}")
                self._cache[path] = {}

        value = self._cache.get(path, {}).get(key)
        # Treat empty strings as None (placeholder values)
        return value if value else None

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def auth_method(self) -> Optional[str]:
        return self._auth_method


# Module-level singleton
vault = VaultSecretResolver()
