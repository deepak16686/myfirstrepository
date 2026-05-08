"""
Normalize every tool entry in config/tools.yaml so url_tailnet and url_funnel
match the path-routed nginx reality (previously, they pointed at
*.deepak-desktop.tailac51e7.ts.net subdomains that don't resolve — only the
bare hostname does, via the Tailscale funnel → nginx-proxy path router).

Line-oriented rewrite: walks the file, tracks which tool block we're inside
via `- id: <slug>` markers, and rewrites exactly the `url_tailnet:` and
`url_funnel:` lines. All comments, blank lines, indentation, and other
fields are preserved byte-for-byte.

Rules:
  * url_tailnet: `https://deepak-desktop.tailac51e7.ts.net/<id>/` (or deep
    link for tools with a known URL prefix like gitlab/jenkins/prometheus).
  * url_funnel:
    - 6 tools with GoDaddy forwarding (grafana, jenkins, sonarqube, nexus,
      vault, gitlab): `https://<id>.deepaksharma.live/`
    - others: same as url_tailnet (still public via the funnel).
  * Non-HTTP tools (postgres-ai, redis, gitlab-runner, gitea-runner): null.
  * url_external is NEVER touched — operator sets those by hand.

Writes a .yaml.bak-<timestamp> sibling before modifying.
"""
from __future__ import annotations

import datetime as _dt
import re
import shutil
import sys
from pathlib import Path

TAILNET_HOST = "deepak-desktop.tailac51e7.ts.net"
GODADDY_CONFIGURED = {"grafana", "jenkins", "sonarqube", "nexus", "vault", "gitlab"}
NON_HTTP_TOOLS = {"postgres-ai", "redis", "gitlab-runner", "gitea-runner"}
DEEP_LINK_PATH = {
    "gitlab": "/gitlab/users/sign_in",
    "jenkins": "/jenkins/login",
    "prometheus": "/prometheus/",
}


def tailnet_url(tid: str) -> str:
    path = DEEP_LINK_PATH.get(tid)
    if path:
        return f"https://{TAILNET_HOST}{path}"
    return f"https://{TAILNET_HOST}/{tid}/"


def funnel_url(tid: str) -> str:
    if tid in GODADDY_CONFIGURED:
        return f"https://{tid}.deepaksharma.live/"
    return tailnet_url(tid)


_ID_RX = re.compile(r"^(\s*- id:\s*)(\S+)\s*$")
_TAILNET_RX = re.compile(r"^(\s*url_tailnet:\s*)(.*)$")
_FUNNEL_RX = re.compile(r"^(\s*url_funnel:\s*)(.*)$")


def rewrite_lines(lines: list[str]) -> tuple[list[str], int]:
    out: list[str] = []
    current_id: str | None = None
    changed_tools: set[str] = set()

    for line in lines:
        m_id = _ID_RX.match(line)
        if m_id:
            current_id = m_id.group(2)
            out.append(line)
            continue

        if current_id:
            m_t = _TAILNET_RX.match(line)
            if m_t:
                prefix = m_t.group(1)
                old_val = m_t.group(2).strip()
                new_val = "null" if current_id in NON_HTTP_TOOLS else tailnet_url(current_id)
                if old_val != new_val:
                    line = f"{prefix}{new_val}\n"
                    changed_tools.add(current_id)
                out.append(line)
                continue
            m_f = _FUNNEL_RX.match(line)
            if m_f:
                prefix = m_f.group(1)
                old_val = m_f.group(2).strip()
                new_val = "null" if current_id in NON_HTTP_TOOLS else funnel_url(current_id)
                if old_val != new_val:
                    line = f"{prefix}{new_val}\n"
                    changed_tools.add(current_id)
                out.append(line)
                continue

        out.append(line)

    return out, len(changed_tools)


def main() -> int:
    here = Path(__file__).resolve()
    backend_root = here.parent.parent
    yaml_path = backend_root / "config" / "tools.yaml"
    if not yaml_path.exists():
        print(f"[fatal] not found: {yaml_path}", file=sys.stderr)
        return 1

    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = yaml_path.with_name(yaml_path.name + f".bak-{ts}")
    shutil.copy2(yaml_path, backup)
    print(f"[backup] {backup.name}")

    original = yaml_path.read_text(encoding="utf-8").splitlines(keepends=True)
    rewritten, n_changed = rewrite_lines(original)

    if rewritten == original:
        print("[done] no changes (every tool already normalized)")
        return 0

    yaml_path.write_text("".join(rewritten), encoding="utf-8")
    print(f"[done] {n_changed} tool(s) updated (see diff `git diff {yaml_path.relative_to(yaml_path.parent.parent)}`)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
