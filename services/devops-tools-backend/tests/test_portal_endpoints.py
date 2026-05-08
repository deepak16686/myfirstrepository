"""End-to-end endpoint tests using FastAPI TestClient.

The background probe task is replaced with a no-op, and the shared
httpx.AsyncClient is swapped for one backed by `httpx.MockTransport` so the
`/health/{tool_id}` force-probe path hits stubs instead of real services.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.integrations.redis_client import HealthCache


def _stub_transport_handler(req: httpx.Request) -> httpx.Response:
    """Default stub: every probe target returns 200."""
    return httpx.Response(200, json={"ok": True})


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    # Patch background_probe_loop to a no-op before import.
    async def _noop(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    from app.routers import portal as portal_router

    monkeypatch.setattr(portal_router, "background_probe_loop", _noop)

    # Import after patching.
    from app.main import app

    # Replace the lifespan-provided http client with a mock-transport one
    # and seed the in-memory cache directly.
    transport = httpx.MockTransport(_stub_transport_handler)
    mock_client = httpx.AsyncClient(transport=transport)
    cache = HealthCache(redis_url="redis://localhost:1", default_ttl_seconds=60)
    # don't call connect() — we want the in-memory fallback
    cache._client = None  # type: ignore[attr-defined]

    with TestClient(app) as c:
        # Override state set by the real lifespan.
        c.app.state.portal_http_client = mock_client
        c.app.state.portal_health_cache = cache
        yield c

    # Close in an event loop.
    asyncio.get_event_loop().run_until_complete(mock_client.aclose())


def test_get_tools_returns_all(client: TestClient) -> None:
    resp = client.get("/api/v1/portal/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for t in data:
        assert "id" in t and "name" in t and "category" in t
        # Credentials MUST be redacted
        assert t["credentials"] in ("none", "<redacted>")


def test_get_tool_by_id(client: TestClient) -> None:
    all_tools = client.get("/api/v1/portal/tools").json()
    tid = all_tools[0]["id"]
    resp = client.get(f"/api/v1/portal/tools/{tid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == tid


def test_get_tool_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/portal/tools/not-a-real-tool")
    assert resp.status_code == 404


def test_health_empty_until_cache_filled(client: TestClient) -> None:
    # Cache is empty by default; endpoint must still return 200.
    resp = client.get("/api/v1/portal/health")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)


def test_force_probe_writes_to_cache(client: TestClient) -> None:
    all_tools = client.get("/api/v1/portal/tools").json()
    # Pick a tool with a non-empty url_internal.
    candidate = next(t for t in all_tools if t.get("url_internal"))
    tid = candidate["id"]

    resp = client.get(f"/api/v1/portal/health/{tid}")
    assert resp.status_code == 200
    status = resp.json()
    assert status["tool_id"] == tid
    # Stub returns 200 -> healthy if expected_status=200 or list that contains 200.
    # Some tools have expect_status like [200,404] -> still healthy.
    assert status["status"] in ("healthy", "degraded")
    assert status["http_status"] == 200

    # Subsequent aggregate call should now include this tool.
    agg = client.get("/api/v1/portal/health").json()
    assert tid in agg


def test_categories_returns_counts(client: TestClient) -> None:
    resp = client.get("/api/v1/portal/categories")
    assert resp.status_code == 200
    cats = resp.json()
    assert isinstance(cats, list)
    assert len(cats) > 0
    for c in cats:
        for key in ("id", "name", "order", "tool_count", "healthy_count", "healthy_pct"):
            assert key in c, f"missing {key} in category {c}"


def test_launch_returns_redirect_url(client: TestClient) -> None:
    all_tools = client.get("/api/v1/portal/tools").json()
    tool_with_url = next(t for t in all_tools if t.get("url_external"))
    resp = client.post(f"/api/v1/portal/launch/{tool_with_url['id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tool_id"] == tool_with_url["id"]
    assert body["redirect_url"]  # non-empty
    assert isinstance(body["requires_auth"], bool)


def test_launch_unknown_tool_404(client: TestClient) -> None:
    resp = client.post("/api/v1/portal/launch/no-such-thing")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Host-based launch URL selection — the public funnel heuristic.
# Added for the single-slot TCP-passthrough design
# (docs/PUBLIC_ACCESS_DEEPAKSHARMA_LIVE.md Appendix B).
# ---------------------------------------------------------------------------


def _find_tool(tools: list[dict], predicate) -> dict:
    """Helper: return the first tool matching predicate (raises if none)."""
    for t in tools:
        if predicate(t):
            return t
    raise AssertionError("no tool matched predicate")


def test_launch_prefers_url_funnel_when_host_is_public(client: TestClient) -> None:
    """When Host matches *.deepaksharma.live AND the tool has url_funnel,
    launch must redirect to url_funnel — NOT url_external (localhost)."""
    all_tools = client.get("/api/v1/portal/tools").json()
    # Pick a tool that HAS both url_funnel and url_external so the contrast
    # is meaningful (Grafana always satisfies this — it's an invariant of the
    # new design that public tools keep their localhost URL too).
    tool = _find_tool(
        all_tools,
        lambda t: bool(t.get("url_funnel")) and bool(t.get("url_external")),
    )
    resp = client.post(
        f"/api/v1/portal/launch/{tool['id']}",
        headers={"Host": "deepaksharma.live"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["redirect_url"] == tool["url_funnel"], (
        f"expected {tool['url_funnel']}, got {body['redirect_url']}"
    )


def test_launch_prefers_url_funnel_when_host_is_subdomain_public(
    client: TestClient,
) -> None:
    """Subdomain of deepaksharma.live (e.g. api.deepaksharma.live) should
    also be treated as public origin."""
    all_tools = client.get("/api/v1/portal/tools").json()
    tool = _find_tool(
        all_tools,
        lambda t: bool(t.get("url_funnel")) and bool(t.get("url_external")),
    )
    resp = client.post(
        f"/api/v1/portal/launch/{tool['id']}",
        headers={"Host": "api.deepaksharma.live"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["redirect_url"] == tool["url_funnel"]


def test_launch_public_host_rejects_tools_without_public_url(
    client: TestClient,
) -> None:
    """Public-origin launches must not fall back to localhost/internal URLs."""
    all_tools = client.get("/api/v1/portal/tools").json()
    tool = _find_tool(
        all_tools,
        lambda t: not t.get("url_funnel")
        and (t.get("url_external") or t.get("url_internal")),
    )
    resp = client.post(
        f"/api/v1/portal/launch/{tool['id']}",
        headers={"Host": "deepaksharma.live"},
    )
    assert resp.status_code == 409
    assert "no launch URL" in resp.json()["detail"]


def test_launch_internal_host_still_prefers_internal(client: TestClient) -> None:
    """Regression: in-cluster callers (Host contains `devops-tools-backend`)
    must still prefer url_internal — the public-host heuristic must not
    accidentally override this."""
    all_tools = client.get("/api/v1/portal/tools").json()
    tool = _find_tool(
        all_tools,
        lambda t: bool(t.get("url_internal")) and bool(t.get("url_external")),
    )
    resp = client.post(
        f"/api/v1/portal/launch/{tool['id']}",
        headers={"Host": "devops-tools-backend:8003"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["redirect_url"] == tool["url_internal"]


def test_launch_host_with_port_is_parsed(client: TestClient) -> None:
    """Edge case: Host header `deepaksharma.live:443` (port suffix) must
    still match the public-origin heuristic."""
    all_tools = client.get("/api/v1/portal/tools").json()
    tool = _find_tool(
        all_tools,
        lambda t: bool(t.get("url_funnel")) and bool(t.get("url_external")),
    )
    resp = client.post(
        f"/api/v1/portal/launch/{tool['id']}",
        headers={"Host": "deepaksharma.live:443"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["redirect_url"] == tool["url_funnel"]


def test_stats_shape(client: TestClient) -> None:
    resp = client.get("/api/v1/portal/stats")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("total", "healthy", "degraded", "down", "unknown", "by_category", "generated_at"):
        assert key in data
    # Counts should sum to total
    total = data["healthy"] + data["degraded"] + data["down"] + data["unknown"]
    assert total == data["total"]


def test_tailscale_status_never_raises(client: TestClient) -> None:
    """Tailscale endpoint must return 200 even if the CLI is missing."""
    # Force "not installed" by pointing the settings path at a bogus binary.
    with patch("shutil.which", return_value=None):
        resp = client.get("/api/v1/portal/tailscale/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] in ("live", "local", "down")


def test_credentials_field_redacted_in_list(client: TestClient) -> None:
    """Explicit regression: the raw `vault:secret/...` pointer must never leak."""
    resp = client.get("/api/v1/portal/tools")
    assert resp.status_code == 200
    for tool in resp.json():
        cred = tool.get("credentials", "")
        assert "vault:" not in cred
        assert "secret/" not in cred


def test_existing_endpoints_still_resolve(client: TestClient) -> None:
    """Regression: all pre-existing endpoints must still be mounted."""
    for path in ("/health", "/api", "/api/v1/status"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} broke (status {resp.status_code})"
