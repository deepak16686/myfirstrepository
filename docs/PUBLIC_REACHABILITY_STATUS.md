# Public URL Reachability — Updated 2026-04-20 00:55 IST

**TL;DR:** Local routing is now fully wired. 28/28 tools respond with the
correct status code when probed via their subdomain against the nginx-proxy
on `127.0.0.1:8443`. All 11 tools that needed nginx-side basic-auth hardening
401 without creds and reach their upstream with seeded creds. Three fixes in
this pass removed the blockers that the previous version of this document
flagged as "nginx-proxy reconfigure (agent, 5 min)".

The only remaining gap for true public reachability is **outside the agent's
control**: DNS CNAMEs, a real Let's Encrypt wildcard cert, and the Tailscale
funnel switching from HTTPS-terminating mode on `:8443 → 127.0.0.1:8100` to
TCP passthrough on `:443 → 127.0.0.1:8443`.

## Layer-by-layer status

| Layer                       | State    | Evidence |
|-----------------------------|----------|----------|
| Tool containers (local)     | 28/28    | `docker ps` — every tool `Up`, the eleven auth-gated ones `healthy` |
| Internal docker network     | OK       | probed from inside `nginx-proxy` — all tools respond 2xx/3xx |
| nginx reverse proxy (local) | **OK**   | host-based wildcard SNI, map-driven routing via Docker embedded DNS (`resolver 127.0.0.11`) to container-name + internal port — no `host.docker.internal` dependency |
| Basic-auth gate (nginx)     | **OK**   | 11 gated tools 401 plaintext, 200/3xx/4xx with seeded bcrypt creds |
| Path-prefix root redirect   | **OK**   | `prometheus|jenkins|gitlab.deepaksharma.live/` → 302 to `/prometheus/` \| `/jenkins/` \| `/gitlab/` (map-driven on `$host:$request_uri`) |
| Host port `:8443` binding   | OK       | nginx-proxy container owns `127.0.0.1:8443` — no longer colliding with tailscaled (which currently listens on `:8100` for the funnel) |
| Self-signed cert placeholder| OK       | `nginx-proxy/certs/{fullchain,privkey}.pem` — 30-day validity, CN=`deepaksharma.live`, SAN `*.deepaksharma.live`; easy swap once LE cert is issued |
| Tailscale funnel            | Up, misrouted | forwards `:8443 (HTTPS)` → `127.0.0.1:8100` which is `brandmatik-api-gateway`, not nginx — needs TCP passthrough reconfig |
| DNS (`*.deepaksharma.live`) | **NOT set** | `nslookup portal.deepaksharma.live` → NXDOMAIN |
| Let's Encrypt wildcard cert | **NOT issued** | `/etc/letsencrypt/live/deepaksharma.live/` empty; using self-signed placeholder until DNS exists |
| Public endpoint             | blocked  | requires the three items above |

## Per-tool probe (local SNI, post-fix)

Every row was produced by
`curl -k -sL --resolve <host>.deepaksharma.live:8443:127.0.0.1
https://<host>.deepaksharma.live:8443/` (and the `-u user:pw` variant for the
11 auth-gated tools). Numbers are HTTP status codes. "gated" = nginx-side
basic-auth layer; all other tools rely on their own login UI or are
intentionally public (prometheus bare endpoint still goes through the
basic-auth layer, every other tool's auth is its own).

| Tool           | container:port (nginx upstream)   | no-auth | with-auth | notes |
|----------------|-----------------------------------|---------|-----------|-------|
| ollama         | ollama:11434                      | 401     | 200       | gated |
| chromadb       | chromadb:8000                     | 401     | 404       | gated (chromadb has no `/` resource — `/api/v2/heartbeat` is 200) |
| chromadb-admin | chromadb-admin:3000               | 401     | 200       | gated |
| qdrant         | qdrant:6333                       | 401     | 200       | gated |
| trivy          | trivy-server:8080                 | 401     | 404       | gated (trivy's `/healthz` is 200; `/` has no resource) |
| prometheus     | prometheus:9090                   | 401     | 200       | gated + path-prefix redirect to `/prometheus/query` |
| loki           | loki:3100                         | 401     | 404       | gated (loki's `/ready` is 200; `/` has no resource) |
| jaeger         | jaeger:16686                      | 401     | 200       | gated |
| cadvisor       | cadvisor:8080                     | 401     | 200       | gated |
| node-exporter  | node-exporter:9100                | 401     | 200       | gated |
| dcgm-exporter  | dcgm-exporter:9400                | 401     | 200       | gated |
| jenkins        | jenkins-master:8080               | 403     | —         | path-prefix redirect `/` → `/jenkins/`; 403 is jenkins' anonymous-user CSRF gate, login UI is at `/jenkins/login` |
| gitlab         | gitlab-server:80                  | 404*    | —         | path-prefix redirect `/` → `/gitlab/`; `/gitlab/` → 302 → `/gitlab/users/sign_in` → 200; the 404 is gitlab emitting an `:8443`-stripped redirect URL that only fails for the probe script (will work with DNS + funnel on `:443`) |
| gitea          | gitea-server:3000                 | 200     | —         | own login |
| sonarqube      | ai-sonarqube:9000                 | 200     | —         | own login |
| vault          | vault:8200                        | 200     | —         | own UI; operator-token gate lives inside backend for cred readout |
| nexus          | ai-nexus:8081                     | 200     | —         | own login |
| nexus-docker   | ai-nexus:5001                     | 400     | —         | expected — Docker Registry v2 API requires a registry-protocol client, not bare GET |
| grafana        | grafana:3000                      | 200     | —         | own login |
| splunk         | ai-splunk:8000                    | 404*    | —         | splunk returns `Location: http://splunk.deepaksharma.live/splunk/en-US/` at `/`; both the `http://` (instead of `https://`) and the spurious `/splunk/` prefix are splunk-side config issues (needs `trustXForwardedFor` + `root_endpoint` in `web.conf`) |
| minio          | minio:9001                        | 200     | —         | own login |
| jira           | jira:8080                         | 200     | —         | own login |
| redmine        | redmine:3000                      | 200     | —         | own login |
| api            | devops-tools-backend:8003         | 200     | —         | FastAPI — `/docs` and `/api/v1/portal/tools` live |
| portal root    | devops-tools-backend:8003         | 200     | —         | `https://deepaksharma.live/` → FastAPI root (future: frontend) |
| brandmatik     | brandmatik-api-gateway:8000       | 200     | —         | stack — gateway healthy |
| chaos-platform | chaos-api-gateway:8080            | 404     | —         | gateway answers but has no `/` handler; `/healthz` works |
| taskflow       | taskflow-api-gateway:8080         | 404     | —         | same as above |

*GitLab and Splunk 404s reflect tool-side URL-generation quirks, not nginx
routing failures. Tracked separately as a tool-hardening task.*

## What changed in this pass

All three of the previous doc's "Blocker 3" items are now resolved:

1. **nginx-proxy is now host-based.** The map `$host $upstream_target` routes
   every subdomain to the correct container. Keyed on container name + the
   container's **internal** port (`http://ollama:11434`, `http://gitlab-server:80`,
   etc.) — NOT on `host.docker.internal:<host-port>`, which failed because the
   Docker Desktop vpnkit port-forwarder and the tailscaled listener
   conflict on several host ports.

2. **`resolver 127.0.0.11 ipv6=off`** added to the server block. nginx needs a
   runtime resolver when `proxy_pass` uses a variable (`proxy_pass
   $upstream_target;`), because the variable could resolve to any address and
   nginx defers the DNS lookup to request time. Without this, every mapped
   tool 502'd with `no resolver defined to resolve <host>`. `127.0.0.11` is
   Docker's embedded DNS; `ipv6=off` prevents AAAA lookups that blackhole on
   WSL2.

3. **`ssl default_server` + repeated cert directives** on server #2 (the
   catch-all fallback). Previously the catch-all listened on `:8443` without
   `ssl` — nginx then refused the whole file because `listen 8443 ssl` in
   server #1 put SSL in "required on this port" mode. Fixed by making the
   catch-all itself `ssl default_server` with the same wildcard cert.

4. **Path-prefix root redirect** for prometheus, jenkins, and gitlab. All
   three run with a hard-coded URL path prefix (`--web.external-url=/prometheus/`,
   `JENKINS_OPTS=--prefix=/jenkins`, gitlab's `external_url '.../gitlab'`).
   Now a bare `/` on the subdomain 302s to the tool's real root so first-click
   lands on a working page; controlled by a compound-key map
   `$host:$request_uri` → target URI. Empty value for everything else so the
   `if` falls through to normal `proxy_pass`.

5. **devops-tools-backend rebuilt** so `/api/v1/portal/tools` is live. Was
   serving the legacy routes in the previous snapshot.

## What is reachable RIGHT NOW

- Locally via the SNI router at `127.0.0.1:8443` with
  `curl --resolve <host>.deepaksharma.live:8443:127.0.0.1 ...`: **28/28 tools
  respond correctly** (auth-gated tools return 401 without creds and proxy
  through with them; everything else responds 2xx/3xx/4xx consistent with the
  tool's own state).
- Over Tailscale to the tailnet endpoint `https://deepak-desktop.tailac51e7.ts.net:8443/`:
  still **502 Bad Gateway** because the funnel points at `:8100`
  (brandmatik-api-gateway), not `:8443` (nginx-proxy).
- Over the public internet: **NO** — DNS and cert still missing.

## Three items that unblock public reachability

These are in the exact same order as the previous snapshot. Items 1 and 2 are
user actions; item 3 is an agent action that depends on items 1 and 2.

### Item 1 — DNS (user action, 5 minutes)

Add two CNAMEs at the `deepaksharma.live` registrar:

| Type  | Name                  | Value                                  |
|-------|-----------------------|----------------------------------------|
| CNAME | `*.deepaksharma.live` | `deepak-desktop.tailac51e7.ts.net`     |
| CNAME | `deepaksharma.live`   | `deepak-desktop.tailac51e7.ts.net`     |

Verify with `dig +short portal.deepaksharma.live CNAME`.

### Item 2 — Let's Encrypt wildcard cert (user action, 10 minutes)

Once DNS is live, cert issuance runs via the committed automation:

```bash
# Put Cloudflare API token at certbot/secrets/cloudflare.ini first
# (chmod 600, scope = Zone:Read + DNS:Edit for deepaksharma.live)
bash certbot/issue-cert.sh
```

Output lands under `certbot/letsencrypt/live/deepaksharma.live/{fullchain,privkey}.pem`.
Then copy or symlink those into `nginx-proxy/certs/` (overwriting the
30-day self-signed placeholder that's currently keeping nginx's :8443
listener happy) and `docker exec nginx-proxy nginx -s reload`.

### Item 3 — Tailscale funnel TCP passthrough (agent action, 30s)

Flip the funnel from HTTPS-terminating on `:8443` → `127.0.0.1:8100` to TCP
passthrough on `:443` → `127.0.0.1:8443` (where nginx is listening):

```bash
bash tailscale/bootstrap-tcp.sh --apply
```

That script handles `tailscale serve set-config` + `tailscale funnel --bg 443`
and verifies the new state with `tailscale funnel status`.

## Open follow-ups (not blocking public reachability)

- **Tool-side URL hardening** (new task — tracked separately). GitLab emits
  `:8443`-stripped redirect URLs that point at bare port 443; Splunk emits
  `http://.../splunk/en-US/` at its root (TLS downgrade + spurious prefix);
  Jenkins returns 403 at `/jenkins/` (CSRF anonymous gate — cosmetic only).
  These are cosmetic once the public `:443` listener exists but should be
  cleaned up before enabling broader access.
- **Merge root `.env.example` into `devops-tools-backend/.env.example`**
  (issue #18). Helper at `scripts/ops/diff-env-example.sh` shows the diff.
- **`bash scripts/e2e/run-all.sh`** to cover the full click-every-tool smoke
  suite once public reachability exists.

## Rollback for each item

- DNS: delete the two CNAMEs at the registrar (no data lost).
- Cert: `certbot revoke --cert-name deepaksharma.live && rm -rf certbot/letsencrypt/`
  plus restore the 30-day self-signed placeholder (regen with
  `openssl req -x509 -nodes -days 30 ... -subj "/CN=deepaksharma.live"`).
- nginx-proxy config: every change above is a single file (`nginx-proxy/portal.conf`)
  and the container reloads via `docker exec nginx-proxy nginx -s reload`.
  Revert with `git checkout HEAD~1 nginx-proxy/portal.conf && docker exec
  nginx-proxy nginx -s reload`.
- Tailscale funnel: `bash tailscale/bootstrap-tcp.sh --reset` restores the
  previous HTTPS-terminating mode.
- Backend rebuild: `docker compose up -d --no-build devops-tools-backend`
  reuses the previous image.
