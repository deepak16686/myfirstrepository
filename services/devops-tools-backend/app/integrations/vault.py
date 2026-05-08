"""
Async HashiCorp Vault client for the DevOps Portal.

Scope
-----
Only KV v2 secret *reads* are implemented. The portal never writes to Vault,
never lists mounts, and never rotates tokens — it reads the secret referenced
by `tool.credentials` (a `vault:secret/...` pointer in ``config/tools.yaml``)
and hands the raw fields to the authenticated operator endpoint.

Graceful degradation
--------------------
If ``VAULT_ADDR`` or ``VAULT_TOKEN`` is not set we log one INFO line at
startup and return ``None`` from ``build_vault_client``. The portal router
then answers the credentials endpoint with ``503`` — identical to the
"operator token not configured" case.

Security
--------
* The Vault token is passed via ``X-Vault-Token`` and is **never** written to
  any log line, INFO or ERROR, regardless of level.
* 403 / 404 responses emit a single WARN with the requested path and the HTTP
  status — the response body (which may echo the token back in bad setups)
  is **not** logged.
* Leading ``secret/`` or ``kv/`` prefixes are stripped before hitting the
  ``v1/secret/data/<path>`` URL — ``tools.yaml`` uses the pointer form
  ``secret/devops/gitlab/root``, but the KV v2 API wants ``devops/gitlab/root``.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class VaultError(Exception):
    """Raised for any non-2xx Vault response or malformed KV v2 payload.

    Attributes
    ----------
    status_code:
        HTTP status from Vault, or ``0`` if the request never reached Vault
        (e.g. timeout, DNS failure).
    message:
        Human-readable, *token-free* summary safe to bubble up to the API
        response body or logs.
    """

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"VaultError(status_code={self.status_code}, message={self.message!r})"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class VaultClient:
    """Minimal async Vault KV v2 reader.

    Lifecycle:
        client = VaultClient(addr="http://vault:8200", token="...", timeout_seconds=3.0)
        data = await client.read_kv("secret/devops/gitlab/root")
        await client.aclose()
    """

    # Prefixes we tolerate on incoming paths because ``tools.yaml`` stores
    # human-readable pointers (``secret/devops/...``) rather than raw KV
    # engine-relative paths.
    _STRIPPED_PREFIXES: tuple[str, ...] = ("secret/", "kv/")

    def __init__(
        self,
        addr: str,
        token: str,
        timeout_seconds: float = 3.0,
    ) -> None:
        if not addr:
            raise ValueError("VaultClient: addr must be non-empty")
        if not token:
            raise ValueError("VaultClient: token must be non-empty")

        self._addr: str = addr.rstrip("/")
        self._token: str = token
        self._timeout: float = float(timeout_seconds)
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._addr,
            timeout=self._timeout,
            headers={"X-Vault-Token": self._token},
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Close the underlying httpx client. Safe to call multiple times."""
        try:
            await self._client.aclose()
        except Exception:  # noqa: BLE001 - defensive, close() must not raise
            pass

    @property
    def addr(self) -> str:
        return self._addr

    # ------------------------------------------------------------------
    # Path normalization
    # ------------------------------------------------------------------

    @classmethod
    def _normalize_path(cls, path: str) -> str:
        """Strip a leading ``secret/`` or ``kv/`` prefix (and surrounding slashes).

        >>> VaultClient._normalize_path("secret/devops/gitlab/root")
        'devops/gitlab/root'
        >>> VaultClient._normalize_path("kv/devops/grafana/admin")
        'devops/grafana/admin'
        >>> VaultClient._normalize_path("/devops/redis/default/")
        'devops/redis/default'
        """
        if not path:
            raise ValueError("vault path must not be empty")
        p = path.strip().lstrip("/")
        for prefix in cls._STRIPPED_PREFIXES:
            if p.startswith(prefix):
                p = p[len(prefix) :]
                break
        return p.strip("/")

    # ------------------------------------------------------------------
    # KV v2 read
    # ------------------------------------------------------------------

    async def read_kv(self, path: str) -> dict[str, str]:
        """Read a KV v2 secret and return the ``data.data`` map.

        Parameters
        ----------
        path:
            Either a bare KV path (``devops/gitlab/root``) or the pointer form
            stored in ``tools.yaml`` (``secret/devops/gitlab/root``). The
            ``secret/`` and ``kv/`` prefixes are stripped transparently.

        Returns
        -------
        dict[str, str]
            The secret fields (e.g. ``{"username": "root", "password": "..."}``).
            All keys and values are stringified — complex KV values should not
            be used for portal credentials anyway.

        Raises
        ------
        VaultError
            On any non-2xx HTTP status, transport failure, or malformed KV v2
            payload (missing ``data`` / ``data.data``).
        """
        try:
            kv_path = self._normalize_path(path)
        except ValueError as exc:
            raise VaultError(status_code=0, message=str(exc)) from exc

        url = f"/v1/secret/data/{kv_path}"

        try:
            response = await self._client.get(url)
        except httpx.TimeoutException as exc:
            raise VaultError(
                status_code=0,
                message=f"vault request timed out after {self._timeout}s",
            ) from exc
        except httpx.HTTPError as exc:
            # Token-free: only the exception type bubbles up.
            raise VaultError(
                status_code=0,
                message=f"vault transport error: {type(exc).__name__}",
            ) from exc

        if response.status_code == 403:
            log.warning("vault_permission_denied path=%s status=403", kv_path)
            raise VaultError(
                status_code=403,
                message="vault permission denied for requested path",
            )
        if response.status_code == 404:
            log.warning("vault_path_not_found path=%s status=404", kv_path)
            raise VaultError(
                status_code=404,
                message="vault path not found",
            )
        if response.status_code >= 400:
            # Deliberately do NOT echo response.text — could include request
            # headers in a proxy-error payload.
            raise VaultError(
                status_code=response.status_code,
                message=f"vault returned HTTP {response.status_code}",
            )

        # KV v2 payload shape: {"data": {"data": {...}, "metadata": {...}}}
        try:
            body: dict[str, Any] = response.json()
        except ValueError as exc:
            raise VaultError(
                status_code=response.status_code,
                message="vault response not valid JSON",
            ) from exc

        outer = body.get("data")
        if not isinstance(outer, dict):
            raise VaultError(
                status_code=response.status_code,
                message="vault response missing 'data' object",
            )
        inner = outer.get("data")
        if not isinstance(inner, dict):
            raise VaultError(
                status_code=response.status_code,
                message="vault response missing 'data.data' object (not KV v2?)",
            )

        # Coerce every field to str; portal credentials are string fields.
        return {str(k): ("" if v is None else str(v)) for k, v in inner.items()}


# ---------------------------------------------------------------------------
# Lifespan factory
# ---------------------------------------------------------------------------


def build_vault_client(settings: Any) -> VaultClient | None:
    """Return a wired ``VaultClient`` or ``None`` when config is incomplete.

    Logs one INFO line on the disabled path so operators know why the
    ``/tools/{id}/credentials`` endpoint will answer ``503``.
    """
    addr = getattr(settings, "vault_addr", "") or ""
    token = getattr(settings, "vault_token", "") or ""
    timeout = float(getattr(settings, "vault_timeout_seconds", 3.0) or 3.0)

    if not addr or not token:
        log.info(
            "vault_client_disabled addr_set=%s token_set=%s "
            "(portal credentials endpoint will return 503)",
            bool(addr),
            bool(token),
        )
        return None

    client = VaultClient(addr=addr, token=token, timeout_seconds=timeout)
    # Deliberately do not log the token or any substring.
    log.info("vault_client_enabled addr=%s timeout_seconds=%s", addr, timeout)
    return client
