"""Classification tests for the health prober.

No live services are contacted — every upstream is stubbed with
`httpx.MockTransport`.
"""
from __future__ import annotations

import asyncio
from typing import Callable

import httpx
import pytest

from app.services.health_prober import probe_all, probe_tool
from app.services.tool_registry import HealthSpec, ToolSpec


def _tool(
    tool_id: str,
    url_internal: str = "http://svc:1",
    *,
    method: str = "GET",
    path: str = "/health",
    expect_status: int | list[int] | str | None = 200,
) -> ToolSpec:
    return ToolSpec(
        id=tool_id,
        name=tool_id,
        category="ai",
        description="t",
        icon="x",
        url_internal=url_internal,
        url_external="http://localhost:1",
        health=HealthSpec(method=method, path=path, expect_status=expect_status),
    )


def _transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_probe_healthy_200() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/health"
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        status = await probe_tool(_tool("t1"), client)
    assert status.status == "healthy"
    assert status.http_status == 200
    assert status.latency_ms is not None
    assert status.error is None


@pytest.mark.asyncio
async def test_probe_degraded_404() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"err": "nope"})

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        status = await probe_tool(_tool("t2"), client)
    assert status.status == "degraded"
    assert status.http_status == 404


@pytest.mark.asyncio
async def test_probe_down_500() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="boom")

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        status = await probe_tool(_tool("t3"), client)
    assert status.status == "down"
    assert status.http_status == 503


@pytest.mark.asyncio
async def test_probe_timeout_classified_down() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated", request=req)

    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        status = await probe_tool(_tool("t4"), client, timeout_seconds=1.0)
    assert status.status == "down"
    assert "timeout" in (status.error or "").lower()


@pytest.mark.asyncio
async def test_probe_list_expect_status_match() -> None:
    """Nexus docker registry expects [200, 401] as healthy."""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="")

    tool = _tool("nexus-dreg", path="/v2/", expect_status=[200, 401])
    async with httpx.AsyncClient(transport=_transport(handler)) as client:
        status = await probe_tool(tool, client)
    assert status.status == "healthy"


@pytest.mark.asyncio
async def test_probe_non_http_method_returns_unknown() -> None:
    tool = ToolSpec(
        id="promtail",
        name="Promtail",
        category="observability",
        description="log shipper",
        icon="send",
        url_internal="",
        url_external="",
        health=HealthSpec(method="docker_ps", path=None, expect_status="running"),
    )
    async with httpx.AsyncClient() as client:
        status = await probe_tool(tool, client)
    assert status.status == "unknown"
    assert "docker" in (status.error or "").lower()


@pytest.mark.asyncio
async def test_probe_empty_url_returns_unknown() -> None:
    tool = _tool("no-url", url_internal="")
    async with httpx.AsyncClient() as client:
        status = await probe_tool(tool, client)
    assert status.status == "unknown"
    assert "url_internal" in (status.error or "")


@pytest.mark.asyncio
async def test_probe_all_concurrent_bounded() -> None:
    """Verify the semaphore actually limits concurrency."""
    concurrent = 0
    peak = 0
    lock = asyncio.Lock()

    async def slow_handler(req: httpx.Request) -> httpx.Response:
        nonlocal concurrent, peak
        async with lock:
            concurrent += 1
            peak = max(peak, concurrent)
        await asyncio.sleep(0.05)
        async with lock:
            concurrent -= 1
        return httpx.Response(200, json={})

    # httpx.MockTransport's handler can be async
    transport = httpx.MockTransport(slow_handler)
    tools = [_tool(f"t{i}") for i in range(25)]

    async with httpx.AsyncClient(transport=transport) as client:
        results = await probe_all(tools, client, timeout_seconds=1.0, max_concurrent=5)

    assert len(results) == 25
    assert all(s.status == "healthy" for s in results.values())
    assert peak <= 5, f"concurrency was not capped (peak={peak})"
