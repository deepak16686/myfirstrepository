#!/usr/bin/env python3
"""
DevOps Portal — Vault Smoke
===========================

Two-phase check:

1. Unauthenticated reachability of Vault at ``$VAULT_ADDR`` (default
   http://localhost:8200) via GET /v1/sys/health. Status codes
   200, 429, 473 are all acceptable — they correspond to
   active+unsealed, standby, and performance-standby respectively.
   429 is also the documented code when a standby refuses requests
   unless ?standbyok=true is set, which we do.

2. Authenticated KV lookup: with ``$VAULT_TOKEN`` set, confirm that
   every tool in ``tools.yaml`` whose ``credentials`` is ``vault:<path>``
   has a readable KV v2 entry at ``<mount>/data/<suffix>``.
   We only check presence — the actual secret payload is NEVER logged
   or persisted.

Output: tabular summary + optional JSON report.
Exit code: 0 only when (1) Vault is reachable AND (2) every mapped
tool has a readable secret. Missing tokens degrade (1) to a WARN and
skip (2); this is exit code 2.

Safe to re-run; no mutation of Vault state.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml


DEFAULT_REGISTRY = Path("devops-tools-backend/config/tools.yaml")
DEFAULT_VAULT_ADDR = "http://localhost:8200"
HTTP_TIMEOUT_SECONDS = 5.0

# Health status codes documented at
# https://developer.hashicorp.com/vault/api-docs/system/health
# 200 active + unsealed; 429 active standby; 473 performance standby;
# 501 not initialized; 503 sealed. We accept 200/429/473 as "alive enough".
ACCEPTABLE_HEALTH_CODES = {200, 429, 473}

# KV v2 has a /data/ segment between mount and key. Our registry uses
# pointers like ``vault:secret/devops/grafana/admin`` where
#   mount  = secret
#   suffix = devops/grafana/admin
# so the read URL is /v1/secret/data/devops/grafana/admin.
# If the user has mounted KV v1 somewhere (unusual here), this check
# will fail and surface it clearly.


# ----------------------------------------------------------------------------
# Data classes
# ----------------------------------------------------------------------------


@dataclass
class VaultCheck:
    kind: str  # HEALTH | KV
    subject: str
    status: str  # OK | FAIL | SKIP | WARN
    http_status: int | None = None
    latency_ms: int | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VaultReport:
    checks: list[VaultCheck] = field(default_factory=list)
    vault_addr: str = ""
    token_present: bool = False

    def exit_code(self) -> int:
        if any(c.status == "FAIL" for c in self.checks):
            return 1
        if any(c.status == "WARN" for c in self.checks):
            return 2
        return 0

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total": len(self.checks),
                "ok": sum(1 for c in self.checks if c.status == "OK"),
                "fail": sum(1 for c in self.checks if c.status == "FAIL"),
                "warn": sum(1 for c in self.checks if c.status == "WARN"),
                "skip": sum(1 for c in self.checks if c.status == "SKIP"),
                "token_present": self.token_present,
                "vault_addr": self.vault_addr,
            },
            "checks": [c.to_dict() for c in self.checks],
        }


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def load_registry(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    tools = data.get("tools") or []
    if not isinstance(tools, list):
        raise ValueError(f"registry {path} 'tools' is not a list")
    return tools


def vault_pointers(tools: list[dict]) -> list[tuple[str, str]]:
    """
    Returns a list of ``(tool_id, pointer)`` tuples for every tool whose
    credentials field starts with ``vault:``.
    """
    out: list[tuple[str, str]] = []
    for t in tools:
        creds = str(t.get("credentials") or "")
        if creds.startswith("vault:"):
            out.append((t.get("id", "<unknown>"), creds))
    return out


def split_pointer(pointer: str) -> tuple[str, str]:
    """
    ``vault:secret/devops/grafana/admin`` -> ("secret", "devops/grafana/admin")
    Raises ``ValueError`` if the pointer is malformed.
    """
    if not pointer.startswith("vault:"):
        raise ValueError(f"not a vault pointer: {pointer!r}")
    path = pointer[len("vault:"):]
    parts = path.strip("/").split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"malformed vault pointer: {pointer!r}")
    return parts[0], parts[1]


def kv_read_url(vault_addr: str, mount: str, key_suffix: str) -> str:
    return f"{vault_addr.rstrip('/')}/v1/{mount}/data/{key_suffix.lstrip('/')}"


def kv_metadata_url(vault_addr: str, mount: str, key_suffix: str) -> str:
    return f"{vault_addr.rstrip('/')}/v1/{mount}/metadata/{key_suffix.lstrip('/')}"


# ----------------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------------


def check_health(
    client: httpx.Client, vault_addr: str
) -> VaultCheck:
    url = f"{vault_addr.rstrip('/')}/v1/sys/health?standbyok=true&sealedcode=503&uninitcode=501&activecode=200"
    t0 = time.perf_counter()
    try:
        resp = client.get(url, timeout=HTTP_TIMEOUT_SECONDS)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        ok = resp.status_code in ACCEPTABLE_HEALTH_CODES
        note = ""
        if not ok:
            note = (
                f"unexpected status {resp.status_code}; "
                f"acceptable={sorted(ACCEPTABLE_HEALTH_CODES)}"
            )
        else:
            try:
                payload = resp.json() or {}
                note = (
                    f"initialized={payload.get('initialized')} "
                    f"sealed={payload.get('sealed')} "
                    f"standby={payload.get('standby')} "
                    f"version={payload.get('version')}"
                )
            except (ValueError, httpx.HTTPError):
                note = "(non-JSON body)"
        return VaultCheck(
            kind="HEALTH",
            subject=url,
            status="OK" if ok else "FAIL",
            http_status=resp.status_code,
            latency_ms=latency_ms,
            note=note,
        )
    except httpx.HTTPError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return VaultCheck(
            kind="HEALTH",
            subject=url,
            status="FAIL",
            latency_ms=latency_ms,
            note=f"{e.__class__.__name__}: {e}",
        )


def check_kv_entry(
    client: httpx.Client,
    vault_addr: str,
    tool_id: str,
    pointer: str,
    token: str,
) -> VaultCheck:
    try:
        mount, suffix = split_pointer(pointer)
    except ValueError as e:
        return VaultCheck(
            kind="KV",
            subject=pointer,
            status="FAIL",
            note=str(e),
        )
    url = kv_read_url(vault_addr, mount, suffix)
    meta_url = kv_metadata_url(vault_addr, mount, suffix)
    t0 = time.perf_counter()
    try:
        # Prefer metadata — it reveals existence + versions without
        # transferring the payload. If metadata is 404, fall back to
        # /data in case the mount is KV v1 (no metadata endpoint).
        resp = client.get(
            meta_url,
            headers={"X-Vault-Token": token},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return VaultCheck(
                kind="KV",
                subject=pointer,
                status="OK",
                http_status=resp.status_code,
                latency_ms=latency_ms,
                note=f"{tool_id}: metadata readable",
            )
        if resp.status_code == 404:
            # Try /data — might be KV v1 or the secret itself might exist
            # without metadata (shouldn't, for v2). Either way, /data 200
            # is proof of presence.
            data_resp = client.get(
                url,
                headers={"X-Vault-Token": token},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if data_resp.status_code == 200:
                return VaultCheck(
                    kind="KV",
                    subject=pointer,
                    status="OK",
                    http_status=data_resp.status_code,
                    latency_ms=latency_ms,
                    note=f"{tool_id}: readable (kv v1?)",
                )
            if data_resp.status_code == 404:
                return VaultCheck(
                    kind="KV",
                    subject=pointer,
                    status="FAIL",
                    http_status=404,
                    latency_ms=latency_ms,
                    note=f"MISSING: {pointer}",
                )
            return VaultCheck(
                kind="KV",
                subject=pointer,
                status="FAIL",
                http_status=data_resp.status_code,
                latency_ms=latency_ms,
                note=f"{tool_id}: /data returned {data_resp.status_code}",
            )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code == 403:
            note = f"{tool_id}: 403 forbidden — VAULT_TOKEN lacks read policy on {pointer}"
        else:
            note = f"{tool_id}: metadata returned {resp.status_code}"
        return VaultCheck(
            kind="KV",
            subject=pointer,
            status="FAIL",
            http_status=resp.status_code,
            latency_ms=latency_ms,
            note=note,
        )
    except httpx.HTTPError as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return VaultCheck(
            kind="KV",
            subject=pointer,
            status="FAIL",
            latency_ms=latency_ms,
            note=f"{tool_id}: {e.__class__.__name__}: {e}",
        )


# ----------------------------------------------------------------------------
# Reporting
# ----------------------------------------------------------------------------


def print_line(c: VaultCheck) -> None:
    lat = f"{c.latency_ms} ms" if c.latency_ms is not None else "-"
    http_status = str(c.http_status) if c.http_status is not None else "-"
    print(f"[{c.status:>4}] {c.kind:<6} {c.subject:<60} {http_status:>5}  {lat:>8}  {c.note}")


def print_summary_table(report: VaultReport) -> None:
    print()
    print("=" * 100)
    print(f"{'KIND':<6} {'SUBJECT':<48} {'STATUS':<6} {'LATENCY':<9} {'NOTE'}")
    print("-" * 100)
    for c in report.checks:
        lat = f"{c.latency_ms} ms" if c.latency_ms is not None else ""
        print(f"{c.kind:<6} {c.subject:<48} {c.status:<6} {lat:<9} {c.note}")
    print("-" * 100)
    ok = sum(1 for c in report.checks if c.status == "OK")
    fail = sum(1 for c in report.checks if c.status == "FAIL")
    warn = sum(1 for c in report.checks if c.status == "WARN")
    skip = sum(1 for c in report.checks if c.status == "SKIP")
    print(
        f"TOTALS   ok={ok}  fail={fail}  warn={warn}  skip={skip}  "
        f"token_present={report.token_present}  vault_addr={report.vault_addr}"
    )
    print("=" * 100)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def run_checks(
    registry_path: Path,
    vault_addr: str,
    token: str | None,
) -> VaultReport:
    tools = load_registry(registry_path)
    pointers = vault_pointers(tools)

    report = VaultReport(vault_addr=vault_addr, token_present=bool(token))

    # httpx.Client is used (sync) — Vault calls are already fast and the
    # aggregate latency is tiny (<= 12 pointers). Keeping it sync also
    # side-steps the Playwright event loop conflict in run-all.sh.
    with httpx.Client(verify=False, headers={"User-Agent": "devops-portal-vault-smoke/1.0"}) as client:
        health = check_health(client, vault_addr)
        report.checks.append(health)
        print_line(health)

        if not token:
            warn = VaultCheck(
                kind="KV",
                subject="(all)",
                status="WARN",
                note="MISSING env VAULT_TOKEN — skipping KV lookups",
            )
            report.checks.append(warn)
            print_line(warn)
            return report

        for tool_id, pointer in pointers:
            c = check_kv_entry(client, vault_addr, tool_id, pointer, token)
            report.checks.append(c)
            print_line(c)

    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="vault_smoke.py",
        description="Verify Vault reachability + presence of every tools.yaml KV pointer.",
    )
    p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument(
        "--vault-addr",
        default=os.environ.get("VAULT_ADDR", DEFAULT_VAULT_ADDR),
        help="Vault URL (defaults to $VAULT_ADDR then http://localhost:8200)",
    )
    p.add_argument("--report", type=Path, default=None, help="Optional JSON output path.")
    p.add_argument("--json", action="store_true", help="Print JSON to stdout after the table.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("VAULT_TOKEN")

    try:
        report = run_checks(args.registry, args.vault_addr, token)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print_summary_table(report)

    if args.json or args.report:
        payload = json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                **report.to_dict(),
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        if args.json:
            print(payload)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(payload, encoding="utf-8")

    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
