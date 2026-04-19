"""Tests for the Vault-backed credentials endpoint.

Everything is hermetic: no real Vault, no real Redis, no network. The test
fixture:
  * stubs the background probe loop to a no-op,
  * swaps ``app.state.portal_http_client`` for a MockTransport client,
  * seeds ``app.state.portal_health_cache`` with an in-memory HealthCache,
  * wires (or deliberately un-wires) ``app.state.vault_client``,
  * overrides ``settings.portal_operator_token`` per test via ``monkeypatch``.

The tests assert the contract in the spec:

  * 401 when header missing
  * 403 when header value wrong
  * 503 when vault client not configured (app.state.vault_client = None)
  * 404 when tool missing
  * 204 when tool has ``credentials: none``
  * 400 when pointer does not start with ``vault:``
  * 200 with mocked VaultClient returning ``{"username":"u","password":"p"}``
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.integrations.redis_client import HealthCache


OPERATOR_TOKEN = "unit-test-operator-token"
OPERATOR_HEADER = "X-Portal-Operator"


# ---------------------------------------------------------------------------
# Fake Vault client
# ---------------------------------------------------------------------------


class _FakeVaultClient:
    """Mirrors the subset of ``VaultClient`` exercised by the router.

    ``read_kv`` returns whatever was seeded via ``set_response`` / raises
    whatever was seeded via ``set_error``. The router only ever calls
    ``read_kv`` and ``aclose``.
    """

    def __init__(self) -> None:
        self._response: dict[str, str] | None = None
        self._error: Exception | None = None
        self.calls: list[str] = []

    def set_response(self, payload: dict[str, str]) -> None:
        self._response = payload
        self._error = None

    def set_error(self, exc: Exception) -> None:
        self._error = exc
        self._response = None

    async def read_kv(self, path: str) -> dict[str, str]:
        self.calls.append(path)
        if self._error is not None:
            raise self._error
        if self._response is None:
            raise AssertionError("FakeVaultClient: no response seeded")
        return dict(self._response)

    async def aclose(self) -> None:  # pragma: no cover - never raises
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _stub_transport_handler(req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})


@pytest.fixture()
def fake_vault() -> _FakeVaultClient:
    """A fresh fake Vault client per test."""
    return _FakeVaultClient()


@pytest.fixture()
def client(
    monkeypatch: pytest.MonkeyPatch,
    fake_vault: _FakeVaultClient,
):
    """TestClient with lifespan overrides.

    Default wiring:
      * operator token = OPERATOR_TOKEN
      * vault_client   = fake_vault

    Tests that want a different state mutate ``app.state`` / ``settings``
    inside the test body via ``monkeypatch`` or direct assignment.
    """
    # Patch the background probe loop BEFORE importing main.
    async def _noop(*args: Any, **kwargs: Any) -> None:
        return None

    from app.routers import portal as portal_router

    monkeypatch.setattr(portal_router, "background_probe_loop", _noop)

    # Seed operator token via the settings singleton the router reads.
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "portal_operator_token", OPERATOR_TOKEN)
    monkeypatch.setattr(app_settings, "portal_operator_header", OPERATOR_HEADER)

    from app.main import app

    transport = httpx.MockTransport(_stub_transport_handler)
    mock_client = httpx.AsyncClient(transport=transport)
    cache = HealthCache(redis_url="redis://localhost:1", default_ttl_seconds=60)
    # Force in-memory fallback — no real Redis.
    cache._client = None  # type: ignore[attr-defined]

    with TestClient(app) as tc:
        tc.app.state.portal_http_client = mock_client
        tc.app.state.portal_health_cache = cache
        tc.app.state.vault_client = fake_vault
        yield tc

    asyncio.get_event_loop().run_until_complete(mock_client.aclose())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_credentials_missing_header_returns_401(client: TestClient) -> None:
    resp = client.get("/api/v1/portal/tools/grafana/credentials")
    assert resp.status_code == 401
    body = resp.json()
    assert "operator" in body["detail"].lower()


def test_credentials_wrong_header_returns_403(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/portal/tools/grafana/credentials",
        headers={OPERATOR_HEADER: "not-the-real-token"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "operator token mismatch"


def test_credentials_vault_client_disabled_returns_503(
    client: TestClient,
) -> None:
    """When app.state.vault_client is None the endpoint must 503."""
    client.app.state.vault_client = None
    resp = client.get(
        "/api/v1/portal/tools/grafana/credentials",
        headers={OPERATOR_HEADER: OPERATOR_TOKEN},
    )
    assert resp.status_code == 503
    assert "disabled" in resp.json()["detail"].lower()


def test_credentials_operator_token_blank_returns_503(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even with a vault client wired, a blank operator token disables the endpoint."""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "portal_operator_token", "")
    # Header is irrelevant — the endpoint short-circuits before auth.
    resp = client.get(
        "/api/v1/portal/tools/grafana/credentials",
        headers={OPERATOR_HEADER: "anything"},
    )
    assert resp.status_code == 503
    assert "disabled" in resp.json()["detail"].lower()


def test_credentials_tool_not_found_returns_404(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/portal/tools/no-such-tool-id/credentials",
        headers={OPERATOR_HEADER: OPERATOR_TOKEN},
    )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_credentials_tool_without_credentials_returns_204(
    client: TestClient,
) -> None:
    """`ollama` has `credentials: none` in the real registry."""
    resp = client.get(
        "/api/v1/portal/tools/ollama/credentials",
        headers={OPERATOR_HEADER: OPERATOR_TOKEN},
    )
    assert resp.status_code == 204
    # 204 responses have no body.
    assert resp.content in (b"", b"null")


def test_credentials_unsupported_scheme_returns_400(
    client: TestClient,
) -> None:
    """`vault` tool itself uses `credentials: env:VAULT_TOKEN` — not `vault:`."""
    resp = client.get(
        "/api/v1/portal/tools/vault/credentials",
        headers={OPERATOR_HEADER: OPERATOR_TOKEN},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "unsupported credentials pointer scheme"


def test_credentials_success_returns_fields(
    client: TestClient,
    fake_vault: _FakeVaultClient,
) -> None:
    """Happy path — operator token OK, Vault returns fields."""
    fake_vault.set_response({"username": "u", "password": "p"})
    resp = client.get(
        "/api/v1/portal/tools/grafana/credentials",
        headers={OPERATOR_HEADER: OPERATOR_TOKEN},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool_id"] == "grafana"
    assert body["source"] == "vault:secret/devops/grafana/admin"
    assert body["fields"] == {"username": "u", "password": "p"}
    assert "retrieved_at" in body and body["retrieved_at"]
    # The path passed to the fake client must have had the `vault:` prefix
    # stripped by the router.
    assert fake_vault.calls == ["secret/devops/grafana/admin"]


def test_credentials_vault_error_returns_503(
    client: TestClient,
    fake_vault: _FakeVaultClient,
) -> None:
    """Vault 403/404/timeout surfaces as a 503 with a token-free message."""
    from app.integrations.vault import VaultError

    fake_vault.set_error(VaultError(status_code=403, message="vault permission denied"))
    resp = client.get(
        "/api/v1/portal/tools/grafana/credentials",
        headers={OPERATOR_HEADER: OPERATOR_TOKEN},
    )
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "vault read failed" in detail.lower()
    assert "403" in detail


def test_redacted_listing_still_hides_pointer(client: TestClient) -> None:
    """Regression: the /tools endpoints must NOT leak `vault:` pointers."""
    resp = client.get("/api/v1/portal/tools/grafana")
    assert resp.status_code == 200
    cred = resp.json().get("credentials", "")
    assert cred in ("none", "<redacted>")
    assert "vault:" not in cred
