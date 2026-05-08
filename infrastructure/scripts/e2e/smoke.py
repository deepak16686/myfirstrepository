#!/usr/bin/env python3
"""
DevOps Portal — Async Smoke Tester
==================================

Walks the canonical tool registry (``services/devops-tools-backend/config/tools.yaml``)
and performs a shallow GET health probe against every tool that advertises a
browser-reachable ``url_external`` + ``health.method == "GET"``.

Design rules (enforced — do not relax without discussion):

- Fully async via ``httpx.AsyncClient`` — one client, many tasks.
- Explicit 5-second per-request timeout; never hang the CI step.
- Each tool probe is independent. One failure does not shortcut peers
  (unless ``--fail-fast`` is passed).
- Exit 0 iff every non-skipped probe passes AND the portal stats endpoint
  reports ``>= 30`` registered tools; exit 1 otherwise.
- Never logs or emits credential values. ``credentials:`` field is never
  resolved here — smoke is an anonymous reachability check.

Run manually (Docker Desktop stack must be UP):

    python infrastructure/scripts/e2e/smoke.py
    python infrastructure/scripts/e2e/smoke.py --only grafana,gitlab --json
    python infrastructure/scripts/e2e/smoke.py --base-external https://ai-dev.tailnet.ts.net

CLI contract is intentionally stable: the companion ``run-all.sh`` and the
``tool_login.py`` driver both shell out here and parse ``--json`` output.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse

import httpx
import yaml


# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

DEFAULT_REGISTRY = Path("services/devops-tools-backend/config/tools.yaml")
DEFAULT_PORTAL_BASE = "http://localhost:8003"
DEFAULT_PORTAL_MIN_TOOLS = 30
HTTP_TIMEOUT_SECONDS = 5.0
# ``httpx`` default follow_redirects is False — we want True here because
# several tools (GitLab, Jenkins) redirect / -> /login on anonymous hits.
FOLLOW_REDIRECTS = True


# ----------------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------------


@dataclass
class ProbeResult:
    """Outcome of a single tool probe — serialisable to JSON."""

    tool_id: str
    status: str  # OK | FAIL | SKIP
    url: str = ""
    http_status: int | None = None
    latency_ms: int | None = None
    note: str = ""
    expected: Any = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # asdict keeps None values — fine for JSON consumers.
        return d


@dataclass
class SmokeReport:
    """Aggregate report across all probes."""

    ok: list[ProbeResult] = field(default_factory=list)
    fail: list[ProbeResult] = field(default_factory=list)
    skip: list[ProbeResult] = field(default_factory=list)
    portal_stats: dict | None = None
    portal_ok: bool = False

    @property
    def all_results(self) -> list[ProbeResult]:
        return self.ok + self.fail + self.skip

    def exit_code(self) -> int:
        if self.fail:
            return 1
        if not self.portal_ok:
            return 1
        return 0

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total": len(self.all_results),
                "ok": len(self.ok),
                "fail": len(self.fail),
                "skip": len(self.skip),
                "portal_ok": self.portal_ok,
            },
            "portal_stats": self.portal_stats,
            "results": [r.to_dict() for r in self.all_results],
        }


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def load_registry(path: Path) -> list[dict]:
    """Load and minimally validate the canonical tool registry."""
    if not path.exists():
        raise FileNotFoundError(f"tool registry not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "tools" not in data:
        raise ValueError(f"registry {path} has no 'tools' key")
    tools = data["tools"]
    if not isinstance(tools, list):
        raise ValueError(f"registry {path} 'tools' is not a list")
    return tools


def rebase_url(url: str, base_external: str) -> str:
    """
    Rewrite the netloc of ``url`` with the netloc from ``base_external``.

    Used when the harness runs against a remote node (e.g. Tailscale funnel)
    but the registry only lists ``localhost:<port>`` entries. Port is
    preserved from the original URL; scheme and host come from the override.
    Empty ``base_external`` is a no-op.
    """
    if not base_external:
        return url
    try:
        origin = urlparse(url)
        base = urlparse(base_external)
        if not origin.netloc:
            return url
        # Preserve the original port (e.g. :3000) but take host + scheme
        # from the override. Tailscale funnels run on the standard TLS
        # port, so if the override has no explicit port we keep the
        # original port; if override explicitly provides a port we use it.
        override_host = base.hostname or origin.hostname or ""
        override_scheme = base.scheme or origin.scheme or "http"
        port = base.port if base.port else origin.port
        netloc = override_host if not port else f"{override_host}:{port}"
        return urlunparse(
            (
                override_scheme,
                netloc,
                origin.path,
                origin.params,
                origin.query,
                origin.fragment,
            )
        )
    except ValueError:
        return url


def status_matches(actual: int, expected: Any) -> bool:
    """Expected may be a single int or a list of ints."""
    if expected is None:
        return False
    if isinstance(expected, int):
        return actual == expected
    if isinstance(expected, (list, tuple, set)):
        return actual in set(expected)
    return False


def select_tools(tools: Iterable[dict], only: list[str] | None) -> list[dict]:
    if not only:
        return list(tools)
    wanted = {s.strip() for s in only if s.strip()}
    return [t for t in tools if t.get("id") in wanted]


# ----------------------------------------------------------------------------
# Probes
# ----------------------------------------------------------------------------


async def probe_tool(
    client: httpx.AsyncClient, tool: dict, base_external: str
) -> ProbeResult:
    """Single-tool health probe. Never raises — maps errors to FAIL."""
    tool_id = tool.get("id", "<unknown>")
    health = tool.get("health") or {}
    method = health.get("method", "")
    url_external = tool.get("url_external") or ""

    if not url_external or method != "GET":
        return ProbeResult(
            tool_id=tool_id,
            status="SKIP",
            note=f"method={method or 'none'} url_external={'(empty)' if not url_external else 'set'}",
        )

    path = health.get("path", "/") or "/"
    expect = health.get("expect_status", 200)
    url = rebase_url(url_external.rstrip("/") + path, base_external)

    t0 = time.perf_counter()
    try:
        resp = await client.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        ok = status_matches(resp.status_code, expect)
        return ProbeResult(
            tool_id=tool_id,
            status="OK" if ok else "FAIL",
            url=url,
            http_status=resp.status_code,
            latency_ms=latency_ms,
            expected=expect,
            note="" if ok else f"status {resp.status_code} != expected {expect}",
        )
    except httpx.TimeoutException:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            tool_id=tool_id,
            status="FAIL",
            url=url,
            latency_ms=latency_ms,
            expected=expect,
            note=f"timeout after {HTTP_TIMEOUT_SECONDS:.1f}s",
        )
    except httpx.ConnectError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            tool_id=tool_id,
            status="FAIL",
            url=url,
            latency_ms=latency_ms,
            expected=expect,
            note=f"connection error: {e.__class__.__name__}",
        )
    except httpx.HTTPError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            tool_id=tool_id,
            status="FAIL",
            url=url,
            latency_ms=latency_ms,
            expected=expect,
            note=f"http error: {e.__class__.__name__}: {e}",
        )


async def probe_portal_stats(
    client: httpx.AsyncClient, portal_base: str, min_tools: int
) -> tuple[bool, dict | None]:
    """Assert the backend's /api/v1/portal/stats reports enough tools."""
    url = portal_base.rstrip("/") + "/api/v1/portal/stats"
    try:
        resp = await client.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return False, {
                "url": url,
                "http_status": resp.status_code,
                "error": f"expected 200, got {resp.status_code}",
            }
        stats = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        return False, {"url": url, "error": f"{e.__class__.__name__}: {e}"}

    # Portal stats schema is flexible — accept any of: {total}, {count},
    # {tools: {total}}, or {tool_count}. Be defensive.
    total = (
        stats.get("total")
        or stats.get("count")
        or stats.get("tool_count")
        or (stats.get("tools") or {}).get("total")
    )
    stats["_url"] = url
    stats["_total_resolved"] = total
    stats["_min_required"] = min_tools
    ok = isinstance(total, int) and total >= min_tools
    return ok, stats


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------


_STATUS_COLOR = {
    "OK": "\033[32m",    # green
    "FAIL": "\033[31m",  # red
    "SKIP": "\033[33m",  # yellow
}
_RESET = "\033[0m"


def _color(status: str) -> str:
    if not sys.stdout.isatty():
        return status
    return f"{_STATUS_COLOR.get(status, '')}{status}{_RESET}"


def print_line(r: ProbeResult) -> None:
    """Per-tool line — stable format, parseable by grep/awk."""
    status_disp = _color(r.status)
    latency = f"{r.latency_ms} ms" if r.latency_ms is not None else "-"
    http_status = str(r.http_status) if r.http_status is not None else "-"
    url = r.url or "-"
    print(f"[{status_disp:>4}] {r.tool_id:<24} {url:<60} {http_status:>5}  {latency:>8}  {r.note}")


def print_summary_table(report: SmokeReport) -> None:
    """GitHub-style table summary printed at the end."""
    print()
    print("=" * 90)
    print(f"{'TOOL':<24} {'STATUS':<8} {'LATENCY':<10} {'NOTE'}")
    print("-" * 90)
    for r in report.all_results:
        latency = f"{r.latency_ms} ms" if r.latency_ms is not None else ""
        note = r.note or ""
        # Strip colour codes for the table
        print(f"{r.tool_id:<24} {r.status:<8} {latency:<10} {note}")
    print("-" * 90)
    total = len(report.all_results)
    print(
        f"TOTALS   ok={len(report.ok)}  fail={len(report.fail)}  "
        f"skip={len(report.skip)}  total={total}  "
        f"portal_ok={report.portal_ok}"
    )
    print("=" * 90)


# ----------------------------------------------------------------------------
# Main entrypoint
# ----------------------------------------------------------------------------


async def run_smoke(
    registry_path: Path,
    base_external: str,
    only: list[str] | None,
    fail_fast: bool,
    portal_base: str,
    portal_min_tools: int,
) -> SmokeReport:
    tools = load_registry(registry_path)
    selected = select_tools(tools, only)
    report = SmokeReport()

    async with httpx.AsyncClient(
        follow_redirects=FOLLOW_REDIRECTS,
        verify=False,  # local self-signed is expected on some ports
        headers={"User-Agent": "devops-portal-smoke/1.0"},
    ) as client:
        # Portal stats first — it's also the registry consumer so a failure
        # here often explains downstream probe failures.
        portal_ok, portal_stats = await probe_portal_stats(
            client, portal_base, portal_min_tools
        )
        report.portal_ok = portal_ok
        report.portal_stats = portal_stats
        portal_note = (
            f"portal stats: total={portal_stats.get('_total_resolved') if portal_stats else '?'} "
            f"min={portal_min_tools} ok={portal_ok}"
        )
        print(f"[{_color('OK' if portal_ok else 'FAIL')}] portal_stats         {portal_note}")

        if fail_fast and not portal_ok:
            print_summary_table(report)
            return report

        # Fan out — all probes run concurrently.
        tasks = [probe_tool(client, t, base_external) for t in selected]
        for coro in asyncio.as_completed(tasks):
            r = await coro
            if r.status == "OK":
                report.ok.append(r)
            elif r.status == "SKIP":
                report.skip.append(r)
            else:
                report.fail.append(r)
            print_line(r)
            if fail_fast and r.status == "FAIL":
                # Cancel remaining tasks — asyncio.as_completed doesn't
                # give us the task handles, so we just stop consuming.
                break

    # Stable ordering for the summary: preserve registry order.
    order = {t["id"]: i for i, t in enumerate(selected)}
    for bucket in (report.ok, report.fail, report.skip):
        bucket.sort(key=lambda r: order.get(r.tool_id, 10**9))

    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="smoke.py",
        description=(
            "Async smoke tester for the DevOps Portal tool registry. "
            "Run AFTER the Docker Desktop stack is up."
        ),
    )
    p.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY,
        help=f"Path to tools.yaml (default: {DEFAULT_REGISTRY})",
    )
    p.add_argument(
        "--base-external",
        default="",
        help="Override scheme+host of every url_external (e.g. https://ai.tailnet.ts.net). Empty = use registry as-is.",
    )
    p.add_argument(
        "--only",
        default="",
        help="Comma-separated list of tool IDs to probe (subset). Empty = all.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report to stdout after the table.",
    )
    p.add_argument(
        "--fail-fast",
        action="store_true",
        help="Abort as soon as the first probe fails.",
    )
    p.add_argument(
        "--portal-base",
        default=DEFAULT_PORTAL_BASE,
        help=f"Portal backend base URL (default: {DEFAULT_PORTAL_BASE})",
    )
    p.add_argument(
        "--portal-min-tools",
        type=int,
        default=DEFAULT_PORTAL_MIN_TOOLS,
        help=f"Minimum tool count asserted against /api/v1/portal/stats (default: {DEFAULT_PORTAL_MIN_TOOLS})",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional path to also write the JSON report to.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    only = [s for s in args.only.split(",") if s.strip()] if args.only else None

    try:
        report = asyncio.run(
            run_smoke(
                registry_path=args.registry,
                base_external=args.base_external,
                only=only,
                fail_fast=args.fail_fast,
                portal_base=args.portal_base,
                portal_min_tools=args.portal_min_tools,
            )
        )
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print_summary_table(report)

    if args.json or args.report:
        payload = json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str)
        if args.json:
            print(payload)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(payload, encoding="utf-8")

    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
