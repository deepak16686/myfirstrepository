# Public URL Reachability — Verified 2026-04-19 22:55 IST

**Short answer:** no tool is reachable on any `*.deepaksharma.live` URL right now.
28/28 tool containers are up and responding inside the docker network; the
public-access layer has three independent blockers.

## TL;DR

| Layer                    | State  | Evidence |
|--------------------------|--------|----------|
| Tool containers (local)  | 28/28  | `docker ps` — all `healthy` for 33+ min |
| Internal docker network  | OK     | probed from inside `nginx-proxy` — all tools respond 200/301/302/303 |
| nginx reverse proxy      | Running **but wrong design** | live config is path-based on `devstack.deepaksharma.live`, committed config (`nginx-proxy/portal.conf`) is host-based wildcards |
| Host port `:8443` binding| Conflicting | Docker port-forward + tailscaled both bound; curl to `127.0.0.1:8443` connects then hangs |
| Tailscale funnel         | Up but **misrouted** | forwards `:8443 (HTTPS)` → `127.0.0.1:8100`, which is `brandmatik-api-gateway`, not nginx |
| DNS (`*.deepaksharma.live`) | NOT set | `nslookup portal.deepaksharma.live` → NXDOMAIN (likewise `grafana`, `deepaksharma.live`, `devstack`) |
| Let's Encrypt wildcard cert | NOT issued | `/etc/letsencrypt/live/deepaksharma.live/` empty |
| Public endpoint check    | 502    | `curl https://deepak-desktop.tailac51e7.ts.net:8443/` → 502 Bad Gateway |

## Per-tool reachability

| Tool            | Container | Internal HTTP | Public URL target                        | Public reachable? |
|-----------------|-----------|---------------|------------------------------------------|-------------------|
| ollama          | up        | 200           | https://ollama.deepaksharma.live         | NO (DNS NXDOMAIN) |
| chromadb        | up        | 200           | https://chromadb.deepaksharma.live       | NO (DNS NXDOMAIN) |
| chromadb-admin  | up        | 200           | https://chromadb-admin.deepaksharma.live | NO (DNS NXDOMAIN) |
| qdrant          | up        | 200           | https://qdrant.deepaksharma.live         | NO (DNS NXDOMAIN) |
| jenkins         | up        | 200 @ /jenkins/login | https://jenkins.deepaksharma.live | NO (DNS NXDOMAIN) |
| gitlab          | up        | healthy (still warming up on `/`) | https://gitlab.deepaksharma.live | NO (DNS NXDOMAIN) |
| gitea           | up        | 200           | https://gitea.deepaksharma.live          | NO (DNS NXDOMAIN) |
| sonarqube       | up        | 200           | https://sonarqube.deepaksharma.live      | NO (DNS NXDOMAIN) |
| vault           | up        | 200 @ /v1/sys/health | https://vault.deepaksharma.live   | NO (DNS NXDOMAIN) |
| trivy           | up        | 200 @ /healthz | https://trivy.deepaksharma.live         | NO (DNS NXDOMAIN) |
| nexus           | up        | 200           | https://nexus.deepaksharma.live          | NO (DNS NXDOMAIN) |
| nexus-docker-registry | up  | 401 (auth required, expected) | https://nexus-docker.deepaksharma.live | NO |
| grafana         | up        | 301 → `/`     | https://grafana.deepaksharma.live        | NO (DNS NXDOMAIN) |
| prometheus      | up        | 200 @ `/prometheus/-/ready` | https://prometheus.deepaksharma.live | NO |
| loki            | up        | 200 @ `/ready`| https://loki.deepaksharma.live           | NO (DNS NXDOMAIN) |
| jaeger          | up        | 200           | https://jaeger.deepaksharma.live         | NO (DNS NXDOMAIN) |
| cadvisor        | up        | 307 → `/containers/` | https://cadvisor.deepaksharma.live| NO |
| node-exporter   | up        | 200 @ /metrics| https://node-exporter.deepaksharma.live  | NO |
| dcgm-exporter   | up        | 200 @ /metrics| https://dcgm-exporter.deepaksharma.live  | NO |
| splunk          | up        | 303 → /en-US/ | https://splunk.deepaksharma.live         | NO (DNS NXDOMAIN) |
| minio           | up        | 200           | https://minio.deepaksharma.live          | NO (DNS NXDOMAIN) |
| jira            | up        | 200           | https://jira.deepaksharma.live           | NO (DNS NXDOMAIN) |
| redmine         | up        | 200           | https://redmine.deepaksharma.live        | NO (DNS NXDOMAIN) |
| devops-tools-backend | up (STALE image) | 200 @ /docs; 404 @ /api/v1/portal/tools | https://api.deepaksharma.live | NO |
| devops-tools-frontend | NOT BUILT | — | https://deepaksharma.live | NO |
| brandmatik      | up (stack) | (multi-service, skipped) | https://brandmatik.deepaksharma.live | NO |
| chaos-platform  | up (stack) | 200 (chaos-portal-ui) | https://chaos-platform.deepaksharma.live | NO |
| taskflow        | up (stack) | 200 (taskflow-api-gateway) | https://taskflow.deepaksharma.live | NO |

**Backend image staleness:** the running `devops-tools-backend` container
serves the *legacy* routes (`/api/v1/chat`, `/api/v1/github-pipeline`,
`/api/v1/commit-history`, …). The `/api/v1/portal/tools` router committed in
`bd36539` and `0797f9d` is NOT live — image predates those commits.
`/openapi.json` confirms 40+ routes, none in the `/portal/` namespace.

## Three independent blockers

### Blocker 1 — DNS (user action, 5 minutes)

Add two CNAME records at the `deepaksharma.live` registrar:

| Type  | Name                  | Value                                  |
|-------|-----------------------|----------------------------------------|
| CNAME | `*.deepaksharma.live` | `deepak-desktop.tailac51e7.ts.net`     |
| CNAME | `deepaksharma.live`   | `deepak-desktop.tailac51e7.ts.net`     |

Verify with `dig +short portal.deepaksharma.live CNAME`.

### Blocker 2 — Let's Encrypt wildcard cert (user action, 10 minutes)

Once DNS is live, cert issuance runs via the committed automation:

```bash
# Put Cloudflare API token at certbot/secrets/cloudflare.ini first
# (chmod 600, scope = Zone:Read + DNS:Edit for deepaksharma.live)
bash certbot/issue-cert.sh
```

Output lands under `certbot/letsencrypt/live/deepaksharma.live/{fullchain,privkey}.pem`.

### Blocker 3 — nginx-proxy + Tailscale funnel reconfigure (I can do, 5 min)

Two issues here:

**3a.** The live `nginx-proxy` container uses path-based routing on a single
hostname `devstack.deepaksharma.live`. Our tools.yaml and committed
`nginx-proxy/portal.conf` expect host-based wildcards
(`gitlab.deepaksharma.live`, `grafana.deepaksharma.live`, …). Need to:
- stop current `nginx-proxy`
- start new one using the committed compose (`nginx-proxy/docker-compose.yml`
  needs to be created — today only the config + certs dir exist there)
- mount the Let's Encrypt cert directory read-only

**3b.** The Tailscale funnel is in HTTPS-terminating mode forwarding to
`127.0.0.1:8100`, which happens to be `brandmatik-api-gateway`. Need TCP
passthrough so the new nginx presents the wildcard cert directly:

```bash
bash tailscale/bootstrap-tcp.sh --apply
```

That script handles both: `tailscale serve set-config` + `tailscale funnel --bg 443`.

## What is reachable RIGHT NOW

**Only the tailnet endpoint:** `https://deepak-desktop.tailac51e7.ts.net:8443/`
currently returns **502 Bad Gateway** because the funnel forwards to
`127.0.0.1:8100` and that doesn't serve nginx. Nothing is reachable from the
public internet, and the tailnet-private endpoint is broken too.

## Fix order

```
1.  (user)  Add DNS records  ──────────────────────────► 5 min
2.  (user)  Run certbot/issue-cert.sh  ─────────────────► 5 min  (depends on 1)
3.  (agent) Create nginx-proxy/docker-compose.yml + restart container ► ~1 min
4.  (agent) Run tailscale/bootstrap-tcp.sh --apply  ──────► ~30 sec
5.  (agent) Rebuild devops-tools-backend image so /api/v1/portal/* exists  ► 2 min
6.  (agent) Start devops-tools-frontend container  ─────► 1 min
7.  (agent) Re-run docs/PUBLIC_REACHABILITY_STATUS.md probes
8.  (agent) bash scripts/e2e/run-all.sh
```

Steps 3–7 are fully automatable once 1–2 land. I'll execute them as one batch
the moment DNS + cert are in place.

## Rollback for each step

- DNS: delete the two CNAMEs at the registrar (no data lost)
- Cert: `certbot revoke --cert-name deepaksharma.live && rm -rf certbot/letsencrypt/`
- nginx-proxy rebuild: `docker compose -f nginx-proxy/docker-compose.yml down` and the current path-based container can be started with its previous `run` command
- Tailscale funnel: `bash tailscale/bootstrap-tcp.sh --reset`
- Backend rebuild: `docker compose up -d --no-build devops-tools-backend` (re-uses the stale image)
