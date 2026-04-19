#!/usr/bin/env python3
"""
seed-vault-basic-auth.py — write nginx basic-auth creds into HashiCorp Vault.

Reads   : scripts/auth/credentials-to-seed.json (chmod 600, gitignored)
Writes  : secret/devops/<tool>/basic-auth (KV v2) with fields
            {username, password, realm, url}
Idempotent: if the secret already exists and --force is NOT passed, the tool
            is skipped with a "skipped — already seeded" log line. With
            --force the secret is overwritten.
Security:
    * Never logs passwords, hashes, or the operator Vault token.
    * Exits non-zero if VAULT_TOKEN is unset.
    * Verifies each write via a read-back (KV v2 returns the same payload
      plus metadata). On mismatch, raises and exits non-zero so CI catches
      Vault misconfigurations.

Verified against:
    * Vault KV v2 API: https://developer.hashicorp.com/vault/api-docs/secret/kv/kv-v2
      (read: GET /v1/<mount>/data/<path>  —  write: POST /v1/<mount>/data/<path>)
    * httpx async client: https://www.python-httpx.org/async/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_JSON_PATH = REPO_ROOT / "scripts" / "auth" / "credentials-to-seed.json"

VAULT_ADDR_DEFAULT = "http://localhost:8200"
KV_MOUNT = "secret"
KV_PATH_TEMPLATE = "devops/{tool}/basic-auth"

# Fields we seed; MUST match what `app/routers/portal.py` surfaces when the
# operator calls GET /portal/tools/{id}/credentials. The CredentialsPanel UI
# walks whatever keys are present and masks each — adding a new field here
# is safe; removing one breaks the UI copy row for that label only.
EXPECTED_FIELDS = ("username", "password", "realm", "url")


# ---------------------------------------------------------------------------
# Logging (plain print — we never pipe secrets through this)
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(f"[seed-vault-basic-auth] {msg}", file=sys.stderr)


def die(msg: str, code: int = 1) -> None:
    log(f"FATAL: {msg}")
    sys.exit(code)


# ---------------------------------------------------------------------------
# Loading the seed JSON
# ---------------------------------------------------------------------------


def load_seed(path: Path) -> list[dict[str, str]]:
    """Load and validate the seed JSON produced by generate-htpasswd.sh."""
    if not path.is_file():
        die(
            f"seed JSON not found at {path}. "
            "Run scripts/auth/generate-htpasswd.sh first."
        )

    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"seed JSON parse error: {exc}")
        return []  # unreachable — die() exits

    creds = doc.get("credentials")
    if not isinstance(creds, list) or not creds:
        die("seed JSON has no 'credentials' array")

    # Type-narrow for mypy-esque robustness.
    assert isinstance(creds, list)

    normalized: list[dict[str, str]] = []
    for i, entry in enumerate(creds):
        if not isinstance(entry, dict):
            die(f"credentials[{i}] is not an object")
        missing = [k for k in ("tool", *EXPECTED_FIELDS) if k not in entry]
        if missing:
            die(f"credentials[{i}] missing fields: {missing}")
        normalized.append({k: str(v) for k, v in entry.items()})
    return normalized


# ---------------------------------------------------------------------------
# Vault KV v2 client (minimal)
# ---------------------------------------------------------------------------


class VaultSeedClient:
    """httpx-backed KV v2 writer — ONLY speaks v1/<mount>/data/<path>."""

    def __init__(self, addr: str, token: str, timeout: float = 5.0) -> None:
        if not addr:
            raise ValueError("vault addr must be non-empty")
        if not token:
            raise ValueError("vault token must be non-empty")
        self._addr = addr.rstrip("/")
        self._client = httpx.Client(
            base_url=self._addr,
            timeout=timeout,
            # Never print this token in tracebacks — httpx redacts headers by
            # default in repr but we won't rely on that; the token is never
            # stringified anywhere in this script.
            headers={"X-Vault-Token": token},
        )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass

    # --- KV v2 operations -------------------------------------------------

    def read(self, path: str) -> dict[str, str] | None:
        """Return the fields at <mount>/data/<path>, or None on 404."""
        r = self._client.get(f"/v1/{KV_MOUNT}/data/{path}")
        if r.status_code == 404:
            return None
        if r.status_code == 403:
            raise RuntimeError(
                f"vault 403 reading {KV_MOUNT}/{path} — token lacks read capability"
            )
        r.raise_for_status()
        body: dict[str, Any] = r.json()
        outer = body.get("data")
        if not isinstance(outer, dict):
            raise RuntimeError("vault response missing 'data'")
        inner = outer.get("data")
        if not isinstance(inner, dict):
            raise RuntimeError("vault response missing 'data.data' (not KV v2?)")
        return {str(k): "" if v is None else str(v) for k, v in inner.items()}

    def write(self, path: str, fields: dict[str, str]) -> None:
        """Write fields to <mount>/data/<path> (creates a new KV v2 version)."""
        payload = {"data": {k: str(v) for k, v in fields.items()}}
        r = self._client.post(f"/v1/{KV_MOUNT}/data/{path}", json=payload)
        if r.status_code == 403:
            raise RuntimeError(
                f"vault 403 writing {KV_MOUNT}/{path} — token lacks create/update capability"
            )
        r.raise_for_status()


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


def seed_one(
    client: VaultSeedClient,
    entry: dict[str, str],
    *,
    force: bool,
) -> str:
    """Seed a single tool. Return status: 'written' | 'skipped' | 'overwritten'."""
    tool = entry["tool"]
    path = KV_PATH_TEMPLATE.format(tool=tool)

    fields = {k: entry[k] for k in EXPECTED_FIELDS}

    existing = client.read(path)
    if existing is not None and not force:
        # All expected fields already present? Treat as fully seeded.
        if all(k in existing for k in EXPECTED_FIELDS):
            return "skipped"
        # Partial prior seed — rewrite so the shape is consistent.
    client.write(path, fields)

    # Read-back verification. Compare just the keys we put — Vault KV v2
    # metadata (created_time, version) lives in a sibling object.
    got = client.read(path)
    if got is None:
        raise RuntimeError(f"vault read-back returned 404 for {path}")
    for k in EXPECTED_FIELDS:
        if got.get(k) != fields[k]:
            # Do NOT include the value in the error — could be a password.
            raise RuntimeError(
                f"read-back mismatch for {path} field={k}"
            )

    return "overwritten" if existing is not None else "written"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed nginx basic-auth creds into Vault KV v2",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing Vault secrets (default: skip if already seeded)",
    )
    parser.add_argument(
        "--addr",
        default=os.environ.get("VAULT_ADDR", VAULT_ADDR_DEFAULT),
        help=f"Vault address (default: env VAULT_ADDR or {VAULT_ADDR_DEFAULT})",
    )
    parser.add_argument(
        "--seed-file",
        default=str(SEED_JSON_PATH),
        help=f"Seed JSON path (default: {SEED_JSON_PATH})",
    )
    args = parser.parse_args(argv)

    token = os.environ.get("VAULT_TOKEN", "").strip()
    if not token:
        die("VAULT_TOKEN env var is unset or empty")

    seed_path = Path(args.seed_file).resolve()
    creds = load_seed(seed_path)
    log(f"loaded {len(creds)} credential entries from {seed_path}")

    client = VaultSeedClient(addr=args.addr, token=token)

    written = overwritten = skipped = 0
    failures: list[tuple[str, str]] = []

    try:
        for entry in creds:
            tool = entry["tool"]
            try:
                status = seed_one(client, entry, force=args.force)
            except Exception as exc:  # noqa: BLE001
                # Log the exception type + sanitized message. Never include
                # the password/username in the log line.
                log(f"FAIL tool={tool} err={type(exc).__name__}: {exc}")
                failures.append((tool, f"{type(exc).__name__}: {exc}"))
                continue

            if status == "written":
                log(f"wrote     tool={tool}  path={KV_MOUNT}/{KV_PATH_TEMPLATE.format(tool=tool)}")
                written += 1
            elif status == "overwritten":
                log(f"overwrite tool={tool}  path={KV_MOUNT}/{KV_PATH_TEMPLATE.format(tool=tool)}")
                overwritten += 1
            elif status == "skipped":
                log(f"skipped   tool={tool}  (already seeded — pass --force to rewrite)")
                skipped += 1
    finally:
        client.close()

    # Summary (never echoes secrets).
    print()
    print("Vault basic-auth seeding summary")
    print("=================================")
    print(f"  wrote new       : {written}")
    print(f"  overwrote       : {overwritten}")
    print(f"  skipped         : {skipped}")
    print(f"  failed          : {len(failures)}")
    if failures:
        print()
        print("Failures:")
        for tool, err in failures:
            print(f"  - {tool}: {err}")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
