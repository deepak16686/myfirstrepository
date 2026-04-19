# Operator Kickoff — `deepaksharma.live` End-to-End

This is the minimum-steps runbook to go from the current committed state
(12 commits on `master`, ahead 21 of `origin/main`) to a fully reachable
public portal at `https://portal.deepaksharma.live` with all 33 tools live.

Every step shows the command, the expected success signal, and the rollback.
All scripts live under `scripts/` and are idempotent.

---

## Prerequisites

- [ ] Docker Desktop running (`docker info` succeeds; `docker context ls` shows `desktop-linux *`)
- [ ] Tailscale installed + logged in (`tailscale status` shows your node)
- [ ] A terminal in `C:\Users\deepak\ai-folder` under Git Bash
- [ ] DNS access to the `deepaksharma.live` zone (registrar or Cloudflare)
- [ ] Cloudflare API token saved at `certbot/secrets/cloudflare.ini`
      (chmod 600, scope: `Zone:Read, DNS:Edit` for the zone)

---

## Step 1 — DNS (user action; one-time)

Add a wildcard + apex record at your registrar / Cloudflare:

| Type  | Name                    | Value                                  | TTL  | Proxy |
|-------|-------------------------|----------------------------------------|------|-------|
| CNAME | `*.deepaksharma.live`   | `deepak-desktop.tailac51e7.ts.net`     | 300  | DNS-only (grey cloud) |
| CNAME | `deepaksharma.live`     | `deepak-desktop.tailac51e7.ts.net`     | 300  | DNS-only |

**Verify:**
```bash
dig +short portal.deepaksharma.live CNAME
dig +short gitlab.deepaksharma.live CNAME
# both should return: deepak-desktop.tailac51e7.ts.net.
```

**Rollback:** delete the two CNAME records at the registrar.

---

## Step 2 — Tailscale Funnel (TCP passthrough, single slot)

```bash
# Enable funnel for the one TCP slot we're allowed.
bash tailscale/bootstrap-tcp.sh
# Expected: "Funnel enabled on :8443"
tailscale serve status
```

**Rollback:**
```bash
tailscale funnel --https=8443 off
tailscale serve reset
```

---

## Step 3 — Let's Encrypt wildcard cert (DNS-01 via Cloudflare)

```bash
# First time only — issues *.deepaksharma.live via Cloudflare DNS API.
bash certbot/issue-cert.sh
# Expected: fullchain.pem + privkey.pem written under certbot/letsencrypt/live/deepaksharma.live/
ls certbot/letsencrypt/live/deepaksharma.live/
```

Renewal is wired via the cron snippet in `certbot/README-crontab.md` — install once
and forget. Manual renewal:

```bash
bash certbot/renew-cert.sh
```

**Rollback:** delete `certbot/letsencrypt/` and reissue. Cert itself can be revoked via
`certbot revoke --cert-name deepaksharma.live`.

---

## Step 4 — Bring up the platform (preserves existing volumes)

```bash
cd devops-tools-backend
# .env must exist with filled values — do not commit it.
# If you haven't merged the root .env.example yet, run the safe diff helper:
cd .. && bash scripts/ops/diff-env-example.sh
# Then copy any missing keys from root .env.example into devops-tools-backend/.env

# Bring up in dependency order:
cd devops-tools-backend
docker compose up -d chromadb ollama
docker compose up -d devops-tools-backend
docker compose ps
```

For the supporting toolchain (GitLab, Nexus, SonarQube, Splunk, Prometheus, Grafana,
Loki, Redmine, MinIO, Plane, Trivy, etc.) the individual compose files live at the
repo root — each has its own `docker-compose.yml` in its folder. A single orchestrator
is intentionally avoided because startup ordering + resource budget differs per host.

Start the ones needed for portal coverage:

```bash
cd ../gitlab             && docker compose up -d
cd ../nexus              && docker compose up -d
cd ../monitoring         && docker compose up -d
cd ../security           && docker compose up -d   # trivy + clair
```

**Rollback:** `docker compose down` in each folder; data persists in named volumes.

---

## Step 5 — nginx SNI router (public-facing :8443)

```bash
cd nginx-proxy
docker compose up -d
docker compose logs -f --tail 20 nginx
# Expected: "Configuration complete; ready for start up"
```

This container is the one behind the Tailscale funnel. It terminates TLS
with the Let's Encrypt cert, does basic-auth on the 10 naked tools
(`scripts/auth/generate-htpasswd.sh` already seeded the `.htpasswd` file), and
reverse-proxies to the right internal service based on `$host`.

**Rollback:** `docker compose down` in `nginx-proxy/`.

---

## Step 6 — E2E verification (automated)

```bash
bash scripts/e2e/run-all.sh
# What it does:
#   1. vault_smoke.py   — confirms Vault is sealed/unsealed and KV v2 reads work
#   2. tool_login.py    — walks every tool's login flow (headless curl/python)
#   3. smoke.py         — hits each public URL, checks 200/302/401+basic-auth
# Output: scripts/e2e/artifacts/report-<timestamp>.json
```

Pass criteria: every tool returns a 2xx / 3xx, basic-auth-gated tools return 401
without header and 200 with the seeded credentials.

**Rollback:** the script is read-only; no cleanup needed.

---

## Step 7 — GitLab repo reconciliation (if repos are missing)

```bash
cd scripts/gitlab
python reconcile.py --dry-run
# Reviews local discovered repos vs GitLab state.
# If anything is missing or divergent, rerun without --dry-run to push.
```

**Rollback:** GitLab's built-in repo history — every push is a ref, nothing is destructive.

---

## Step 8 — `.env.example` merge (final cleanup)

```bash
bash scripts/ops/diff-env-example.sh
# Reads /tmp/env-only-in-root.txt — every key listed there needs a decision:
#   (a) copy the KEY=<value> line into devops-tools-backend/.env.example
#   (b) copy the KEY=<value> line into devops-tools-backend/.env (live values)
#   (c) drop it (stale / obsolete)
# Once done:
git rm .env.example
git add devops-tools-backend/.env.example
git commit -m "Consolidate root .env.example into backend"
```

---

## Follow-up: rotate leaked SonarQube tokens (CRITICAL)

Commit `c2f0936` scrubbed 20 `squ_*` tokens from `sonarqube-projects.csv`,
but they were present in git history prior to that commit. Rotate them in
SonarQube (Administration → Security → Users → $user → Tokens → Revoke,
then generate new ones). Until rotation, treat those tokens as compromised.

---

## Status at start of this runbook

- Commits: 12 on `master`, ahead 21 of `origin/main`, behind 2.
- Working tree: `.env.example` (root, untracked) only — intentional, see Step 8.
- All nginx configs, tailscale bootstrap, certbot automation, portal backend,
  portal frontend, and E2E harness are committed and ready to run.
- Unblocked tasks: #8 (Step 4), #9 (Step 6), #14 (Steps 1-3), #18 (Step 8).

## Quick status check

```bash
git log --oneline origin/main..HEAD    # 21 commits we added
git status --short                      # should show only .env.example
ls scripts/ops/ tailscale/ certbot/ scripts/e2e/ scripts/auth/ nginx-proxy/ | head -20
```
