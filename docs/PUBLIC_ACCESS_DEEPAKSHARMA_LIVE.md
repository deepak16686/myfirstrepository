# Public access runbook — `*.deepaksharma.live` for ALL 33 DevOps portal tools

**Status: supersedes** `docs/TAILSCALE_DEEPAKSHARMA_LIVE.md` for the public
surface. The prior doc covered a 3-slot HTTPS funnel design (portal + grafana +
gitlab public, other 30 tools tailnet-only). This runbook lifts that cap by
routing every tool through a **single Tailscale Funnel slot in TCP-passthrough
mode**, with TLS terminated by host nginx using a Let's Encrypt wildcard cert.

> The tailnet-only surface from the prior doc is still valid — every tool still
> has `url_tailnet: https://<id>.deepak-desktop.tailac51e7.ts.net` in
> `tools.yaml` for intra-tailnet access. Nothing was removed; this doc is an
> additive public layer.

---

## Why this design (short version)

| Limitation | Prior design | This design |
|---|---|---|
| Tailscale Funnel free-tier host:port cap | 3 slots used | 1 slot used (TCP passthrough) |
| Public tool count | 3 | 28 |
| TLS termination | tailscaled (Tailscale-issued cert, tailnet names only) | host nginx (Let's Encrypt wildcard, `*.deepaksharma.live`) |
| SNI dispatch | N/A (one host per slot) | Nginx `map $host $upstream_target` |
| Cert renewal | automatic (Tailscale) | `certbot renew` every 60-90 days |

Key insight: a single `tailscale funnel --bg 443` entry counts as ONE slot,
and in **TCP-passthrough mode** (`TCPForward` + `TerminateTLS: ""`), the
tailscaled daemon just forwards bytes — the client's TLS handshake is
negotiated downstream by host nginx. Nginx sees the real SNI (`$host`) and
routes accordingly.

**Verified against:**
- Funnel port cap: <https://tailscale.com/kb/1223/funnel-availability> (section
  "Funnel ports") — allowed ports are 443, 8443, 10000.
- Serve config schema: <https://tailscale.com/kb/1242/tailscale-serve#saving-configurations>
- TCPForward + TerminateTLS semantics: `tailscale serve --help` + the
  `ipn.ServeConfig` Go type at
  <https://github.com/tailscale/tailscale/blob/main/ipn/serve.go>.
- DNS-01 wildcard requirement: <https://letsencrypt.org/docs/challenge-types/#dns-01-challenge>
  — "Wildcard certificates ... can only be issued using the dns-01 challenge."

---

## Components modified

| File | Change |
|---|---|
| `devops-tools-backend/config/tools.yaml` | `url_funnel` set on all 28 HTTP-serving tools (was: 4). |
| `tailscale/serve-config.json` | Replaced with single-entry TCP passthrough. |
| `tailscale/bootstrap-tcp.sh` | NEW — sibling to `bootstrap-funnel.sh`; applies the TCP config. |
| `nginx-proxy/portal.conf` | Rewritten as wildcard-SNI router on :8443 with TLS termination. |
| `devops-tools-backend/app/routers/portal.py` | `POST /launch/{tool_id}` prefers `url_funnel` when the request Host matches `*.deepaksharma.live`. |
| `devops-tools-backend/tests/test_portal_endpoints.py` | New test: launch picks `url_funnel` when called via the public Host header. |
| `devops-tools-backend/frontend/src/components/tools/UrlChips.tsx` | No change needed — renders PUBLIC chip wherever `url_funnel` is set. |

---

## Phase A — DNS (one-time)

At the registrar that owns **deepaksharma.live**:

| Record | Type | Value | TTL |
|---|---|---|---|
| `*.deepaksharma.live` | CNAME | `deepak-desktop.tailac51e7.ts.net.` | 300 |
| `deepaksharma.live` | CNAME (ALIAS / ANAME) | `deepak-desktop.tailac51e7.ts.net.` | 300 |

**Apex caveat.** A strict `CNAME` at the apex (the "zone root") is
non-compliant with RFC 1035. Modern registrars support it as **ALIAS**
(Route 53), **ANAME** (DNSimple, Namecheap), or **CNAME flattening**
(Cloudflare). If your registrar doesn't:

1. Pick a permanent wildcard-reachable name like `portal.deepaksharma.live`,
2. Make it a `CNAME` to the tailnet MagicDNS name,
3. Use the apex for a 301 redirect (Cloudflare Page Rule / registrar redirect
   service) to `https://portal.deepaksharma.live`.

**Low TTL during setup.** Keep 300s until the design is stable; then bump to
3600+ to reduce lookups.

**Verify:**
```bash
dig CNAME grafana.deepaksharma.live +short
# expected: deepak-desktop.tailac51e7.ts.net.
dig CNAME deepaksharma.live +short
# expected: deepak-desktop.tailac51e7.ts.net.   (or IP if ALIAS flattened)
```

---

## Phase B — Let's Encrypt wildcard cert (one-time + 60-day renewal)

Wildcards **require** the `dns-01` challenge. Pick the path that matches the
registrar's DNS API:

### Option 1 — Cloudflare DNS (recommended)

1. Create an API token (Zone -> DNS -> Edit) scoped only to `deepaksharma.live`.
2. Put the token in an INI file with strict perms:
   ```ini
   # ~/.secrets/certbot/cloudflare.ini   (mode 0600)
   dns_cloudflare_api_token = REDACTED
   ```
   ```bash
   mkdir -p ~/.secrets/certbot
   chmod 600 ~/.secrets/certbot/cloudflare.ini
   ```
3. Install certbot + the Cloudflare plugin:
   ```bash
   sudo apt install certbot python3-certbot-dns-cloudflare   # Ubuntu/WSL
   ```
4. Issue the cert:
   ```bash
   sudo certbot certonly \
     --dns-cloudflare \
     --dns-cloudflare-credentials ~/.secrets/certbot/cloudflare.ini \
     --preferred-challenges dns \
     -d '*.deepaksharma.live' -d 'deepaksharma.live' \
     --agree-tos --email deepakdce2009@gmail.com
   ```
5. Certbot writes:
   * `/etc/letsencrypt/live/deepaksharma.live/fullchain.pem`
   * `/etc/letsencrypt/live/deepaksharma.live/privkey.pem`

### Option 2 — Route 53 (AWS)

Install the IAM user with `route53:ChangeResourceRecordSets` + `route53:GetChange`
permissions, then:
```bash
sudo certbot certonly --dns-route53 \
  -d '*.deepaksharma.live' -d 'deepaksharma.live' \
  --agree-tos --email deepakdce2009@gmail.com
```

### Option 3 — Namecheap / registrar WITHOUT DNS API

Fallback to interactive mode (not auto-renewable):
```bash
sudo certbot certonly --manual --preferred-challenges dns-01 \
  -d '*.deepaksharma.live' -d 'deepaksharma.live' \
  --agree-tos --email deepakdce2009@gmail.com
```
Paste the `_acme-challenge.deepaksharma.live` TXT record when prompted.

### Option 4 — Docker-based, no host certbot

Use the official `certbot/dns-cloudflare` image; keeps the host clean:
```bash
docker run --rm -it \
  -v letsencrypt:/etc/letsencrypt \
  -v ~/.secrets/certbot/cloudflare.ini:/secrets/cloudflare.ini:ro \
  certbot/dns-cloudflare certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /secrets/cloudflare.ini \
    -d '*.deepaksharma.live' -d 'deepaksharma.live' \
    --agree-tos --email deepakdce2009@gmail.com
```

### Auto-renewal

Certbot 2.x ships a systemd timer that runs `certbot renew` twice daily. Add a
deploy hook so nginx-proxy reloads on rotation:
```bash
# /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh   (chmod 0755)
#!/usr/bin/env bash
docker exec nginx-proxy nginx -s reload
```
(If you use the docker-based certbot, put the hook inside the certbot image's
`post-hook` or run a wrapper cron.)

**Verify renewal dry run:**
```bash
sudo certbot renew --dry-run
```

---

## Phase C — nginx-proxy container update

The nginx-proxy container must:

1. **Mount `/etc/letsencrypt`** so it can read the cert.
2. **Bind host port 8443** (not 443 — Tailscale owns 443 publicly).
3. **Include `portal.conf`** in its `nginx.conf`.

Edit `devops-tools-backend/docker-compose.yml` (or the existing compose file
that defines `nginx-proxy`):

```yaml
  nginx-proxy:
    image: nginx:1.27-alpine
    container_name: nginx-proxy
    restart: unless-stopped
    ports:
      - "127.0.0.1:8443:8443"   # Tailscale TCPForward lands here
    volumes:
      - ./nginx-proxy/portal.conf:/etc/nginx/conf.d/portal.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      # Optional: basic auth password file for unauth'd tools
      # - ./nginx-proxy/htpasswd:/etc/nginx/htpasswd:ro
    networks:
      - ai-platform-net
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8443/healthz"]
      interval: 30s
      timeout: 5s
      retries: 3
```

**Bring up / reload:**
```bash
docker compose -f devops-tools-backend/docker-compose.yml up -d nginx-proxy
# OR (if already running):
docker compose -f devops-tools-backend/docker-compose.yml restart nginx-proxy
# Verify config inside the container:
docker exec nginx-proxy nginx -t -c /etc/nginx/nginx.conf
docker exec nginx-proxy nginx -s reload
```

**Verify the cert is readable:**
```bash
docker exec nginx-proxy \
  openssl x509 -in /etc/letsencrypt/live/deepaksharma.live/fullchain.pem \
  -noout -text | grep -E 'Subject:|DNS:'
```

You should see `DNS:*.deepaksharma.live, DNS:deepaksharma.live`.

**Important caveat on `127.0.0.1` upstreams inside a container.** The nginx
upstreams in `portal.conf` all point to `127.0.0.1:<port>`. These are
**host-loopback ports**, not container-loopback. For this to work on Linux,
the nginx-proxy container must either:

- Run with `network_mode: host`, OR
- Have access to the host loopback via `extra_hosts: ["host.docker.internal:host-gateway"]`
  AND the map must be rewritten to `http://host.docker.internal:<port>`.

Docker Desktop on Windows/Mac makes `host.docker.internal` resolve by default.
If you deploy this config elsewhere, either switch to `network_mode: host` or
rewrite the map to use the container names on `ai-platform-net` (e.g.
`grafana:3000` instead of `127.0.0.1:3000`). The `portal.conf` comments call
this out at the top.

---

## Phase D — Tailscale bring-up

On the host that runs tailscaled (Windows tray OR WSL `sudo tailscale up`):

1. Confirm you're signed in:
   ```bash
   tailscale status
   ```

2. Apply the new TCP-passthrough serve config:
   ```bash
   cd ~/ai-folder   # wherever the repo lives
   ./tailscale/bootstrap-tcp.sh --apply
   ```

   The script:
   - Reads `tailscale/serve-config.json` (template with `${MAGIC_DNS_NAME}`).
   - Resolves the MagicDNS name from `tailscale status --json`.
   - Renders to `/tmp/serve-config.tcp.rendered.json`.
   - `tailscale serve set-config <rendered>`.
   - `tailscale funnel --bg 443` (belt-and-braces — AllowFunnel already in config).
   - Prints status + smoke-curls.

3. Verify:
   ```bash
   tailscale funnel status
   # expected: exactly one entry: <your-magic-dns>:443 -> TCPForward 127.0.0.1:8443
   tailscale serve status
   ```

**Windows host vs WSL — which one runs tailscaled?**

- **Windows tray install** (you installed Tailscale from <https://tailscale.com/download/windows>):
  the tailscaled daemon is on Windows. Run `bootstrap-tcp.sh` from WSL but
  point it at the Windows CLI:
  ```bash
  export TAILSCALE_CLI="/mnt/c/Program Files/Tailscale/tailscale.exe"
  ./tailscale/bootstrap-tcp.sh --apply
  ```
  The serve config path must be a Windows-visible path; the script already
  writes the rendered file to `${TMPDIR:-/tmp}` — on WSL that's `/tmp`, which
  Windows-Tailscale can read via `\\wsl$\...`. If that fails, set
  `TMPDIR=/mnt/c/Users/deepak/AppData/Local/Temp`.

- **WSL install** (`curl -fsSL https://tailscale.com/install.sh | sh`):
  tailscaled runs inside WSL. `bootstrap-tcp.sh` finds the CLI on `PATH`
  automatically.

Only ONE of these should run at a time — overlapping installs create two
tailnet nodes with different MagicDNS names.

---

## Phase E — Smoke test

### Sample curls

```bash
# Portal front door (frontend)
curl -I https://deepaksharma.live
# API
curl -I https://api.deepaksharma.live/health
# Tools (pick any 3-5 to verify end-to-end)
curl -I https://grafana.deepaksharma.live          # -> 302 /login
curl -I https://gitlab.deepaksharma.live/-/readiness
curl -I https://sonarqube.deepaksharma.live/api/system/status
curl -I https://prometheus.deepaksharma.live/-/ready
curl -I https://jaeger.deepaksharma.live/
```

### Automated smoke for every `url_funnel`

One-liner that reads `tools.yaml` and curls every public URL in parallel:

```bash
python3 - <<'PY' | xargs -P 16 -I{} bash -c 'url="{}"; printf "%s  %s\n" "$(curl -sS -I -L --max-time 10 -o /dev/null -w "%{http_code}" "$url")" "$url"'
import yaml
d = yaml.safe_load(open('devops-tools-backend/config/tools.yaml'))
for t in d['tools']:
    u = t.get('url_funnel')
    if u:
        print(u)
PY
```

Acceptable codes per tool: most should return `200` or a redirect code
(`301`/`302`/`307`). Some return `401` (auth wall) or `404` (tool returns 404
on `/` — that's the app, not our proxy).

### Verify cert

```bash
echo | openssl s_client -servername grafana.deepaksharma.live \
  -connect grafana.deepaksharma.live:443 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```
Expected `subject=... CN=*.deepaksharma.live` (or similar) and `issuer` issued
by Let's Encrypt (`R3` / `E1` / `R10` / `R11` depending on the issuing CA chain
in use at the time).

---

## Phase F — Security hardening (CRITICAL)

These tools have **no built-in auth** and/or leak internals — protect them
before public exposure. Every item here has been cross-checked against
upstream docs.

| Tool | Problem | Recommended mitigation |
|---|---|---|
| **Ollama** (11434) | No native auth prior to 0.1.43+. | Enable `OLLAMA_HOST=0.0.0.0` + reverse-proxy basic auth, OR `OLLAMA_API_KEY` via latest version, OR front with oauth2-proxy / Cloudflare Access. |
| **ChromaDB** (8005) | No auth by default. | Set `CHROMA_SERVER_AUTHN_PROVIDER=chromadb.auth.basic_authn.BasicAuthenticationServerProvider` + `CHROMA_SERVER_AUTHN_CREDENTIALS=<bcrypt-htpasswd>` (see <https://docs.trychroma.com/deployment/auth>). |
| **Qdrant** (6333) | No auth by default. | `QDRANT__SERVICE__API_KEY=<random>` in env; clients send `api-key` header. |
| **Trivy server** (8183) | No auth. | Nginx basic auth (see below). |
| **Prometheus** (9090) | No auth. | Nginx basic auth. Also disable `/-/reload` if exposing. |
| **Loki** (3100) | No auth. | Nginx basic auth. |
| **Jaeger query** (16686) | No auth. | Nginx basic auth. |
| **cAdvisor** (8182) | No auth; exposes container listing + host metrics. | Nginx basic auth **plus** IP restrict. |
| **node-exporter** (9100) | No auth; leaks `/proc` details. | Nginx basic auth **plus** IP restrict to tailnet peers. |
| **dcgm-exporter** (9400) | No auth; leaks GPU telemetry. | Nginx basic auth **plus** IP restrict. |

### Nginx basic-auth — implemented (maps + Vault-backed creds)

The 11 naked tools above are hard-gated at the nginx edge via the
**variable-driven `auth_basic` pattern** (nginx >= 1.3.10; the `nginx:1.27-alpine`
base has it). Two `map` blocks in `nginx-proxy/portal.conf` — `$auth_realm`
and `$auth_file` — feed the directives inside the main `location /` block:

```nginx
map $host $auth_realm {
    default                           off;              # literal `off` == "auth disabled"
    ollama.deepaksharma.live          "Ollama (auth required)";
    chromadb.deepaksharma.live        "ChromaDB (auth required)";
    # ... 9 more ...
}

map $host $auth_file {
    default                           /etc/nginx/auth/htpasswd;
    # all 11 protected hosts point at the same file
}

server {
    # ...
    location / {
        auth_basic            $auth_realm;
        auth_basic_user_file  $auth_file;
        proxy_pass            $upstream_target;
        # ...
    }
}
```

Why this over the `if` / `error_page 418` / named-location idiom: `map` is
evaluated once at request admission and doesn't invoke "if is evil"
(<https://nginx.org/en/docs/faq/if_is_evil.html>). The trick is that
`$auth_realm` resolves to the **literal string `off`** for unprotected hosts
(NOTE: unquoted in the map value; if you quote it nginx treats it as a realm
string and prompts for creds on every request).

#### One-shot credential provisioning

Run the generator — produces strong random 32-char passwords, writes
bcrypt-hashed entries to `nginx-proxy/htpasswd` (gitignored), and writes
plaintext pairs to `scripts/auth/credentials-to-seed.json` (gitignored,
chmod 600):

```bash
./scripts/auth/generate-htpasswd.sh
```

Example output:

```
DevOps Portal basic-auth credentials generated
===============================================
TOOL              USERNAME          PASSWORD-FINGERPRINT
----              --------          --------------------
ollama            ollama            ****a3b2
chromadb          chromadb          ****91ce
...
```

Then seed them into Vault so the portal's CredentialsPanel can surface them
to the operator via the `/api/v1/portal/tools/<id>/credentials` endpoint:

```bash
export VAULT_TOKEN=hvs....                  # operator token
python scripts/auth/seed-vault-basic-auth.py

# Or force-rewrite existing secrets (rotation):
python scripts/auth/seed-vault-basic-auth.py --force
```

The Python script is idempotent by default (skips already-seeded secrets),
reads back every write to verify, and never logs passwords.

#### Manual fallback (if you can't run the script)

If the generator isn't available, you can still build the htpasswd by hand
— `htpasswd` ships with `apache2-utils` / `httpd-tools`. **bcrypt only**
(`-B`); never MD5 (`$apr1$`) or plain.

```bash
# One-shot, all 11 tools, random passwords:
for tool in ollama chromadb chromadb-admin qdrant trivy prometheus loki \
            jaeger cadvisor node-exporter dcgm-exporter; do
    if [ ! -f nginx-proxy/htpasswd ]; then
        htpasswd -cbB -C 12 nginx-proxy/htpasswd "$tool" "$(openssl rand -hex 16)"
    else
        htpasswd -bB  -C 12 nginx-proxy/htpasswd "$tool" "$(openssl rand -hex 16)"
    fi
done
chmod 600 nginx-proxy/htpasswd
```

Then MANUALLY write each `{username, password, realm, url}` tuple to Vault
at `secret/devops/<tool>/basic-auth` via `vault kv put` — the seeder script
is strongly preferred because it handles idempotency and read-back.

#### Reload nginx

After the htpasswd is in place, tell the container to reload (no downtime):

```bash
docker exec nginx-proxy nginx -t          # validate
docker exec nginx-proxy nginx -s reload   # graceful reload
```

#### Rotation

Regenerating is a "blow it away and reseed" operation — pass `--force` to
both tools. All 11 passwords rotate at once:

```bash
./scripts/auth/generate-htpasswd.sh --force
python scripts/auth/seed-vault-basic-auth.py --force
docker exec nginx-proxy nginx -s reload
```

### IP allow-list for noisiest endpoints

The commented `if ($host ~* ^(prometheus|cadvisor|node-exporter|dcgm-exporter)...)` block
in `portal.conf` shows how to allow only the Tailscale CGNAT range (`100.64.0.0/10`)
plus an explicit office IP. Uncomment on deployment. This is orthogonal to
basic auth — prefer running **both** for the exporters.

---

## Phase G — Rollback

### Tier 1 — soft: hide new URLs in portal UI only

```bash
git checkout -- devops-tools-backend/config/tools.yaml
docker exec devops-tools-backend pkill -HUP gunicorn 2>/dev/null \
  || docker compose -f devops-tools-backend/docker-compose.yml restart devops-tools-backend
```

Public funnel is still alive, but the frontend no longer renders the PUBLIC
chip. (Useful if one tool's URL breaks — revert, investigate, re-apply.)

### Tier 2 — medium: tear down the public surface, keep tailnet

```bash
./tailscale/bootstrap-tcp.sh --reset
```

Equivalent to:
```bash
tailscale funnel reset
tailscale serve reset
```

Public subdomains return DNS-resolvable-but-unreachable (TCP RST on :443).
Tailnet access over `<id>.deepak-desktop.tailac51e7.ts.net` depends on whether
you then re-apply the OLD serve-config:
```bash
./tailscale/bootstrap-funnel.sh --apply    # re-enable the 3-slot HTTPS design
```

### Tier 3 — hard: full stop

```bash
./tailscale/bootstrap-tcp.sh --reset
docker compose -f devops-tools-backend/docker-compose.yml stop nginx-proxy
# Optional: sign out of the tailnet entirely
tailscale down
```

DNS still points at the tailnet name but nothing listens. To also remove the
wildcard cert (if you suspect key leakage):
```bash
sudo certbot revoke --cert-path /etc/letsencrypt/live/deepaksharma.live/cert.pem \
  --reason keycompromise
sudo certbot delete --cert-name deepaksharma.live
```

---

## Appendix A — Relationship to previous design

The previous runbook `docs/TAILSCALE_DEEPAKSHARMA_LIVE.md` (delivered by agent
`ad431b75a9b713690`) describes the 3-slot HTTPS funnel design. Both configs
coexist on disk:

| File | Owned by which design |
|---|---|
| `tailscale/serve-config.json` | *this* runbook (TCP passthrough) — was: 3-slot HTTPS |
| `tailscale/bootstrap-funnel.sh` | previous runbook (3-slot HTTPS design) |
| `tailscale/bootstrap-tcp.sh` | *this* runbook |
| `nginx-proxy/portal.conf` | *this* runbook (wildcard SNI) — was: 3 per-host server blocks |

Only ONE of `bootstrap-funnel.sh --apply` or `bootstrap-tcp.sh --apply` can be
active at a time (both call `tailscale serve set-config`, which is a
declarative replace). The two scripts cannot be layered.

If you want to switch back to the 3-slot design:

```bash
./tailscale/bootstrap-tcp.sh --reset
git checkout HEAD~1 -- tailscale/serve-config.json nginx-proxy/portal.conf
./tailscale/bootstrap-funnel.sh --apply
```

---

## Appendix B — Why the backend prefers `url_funnel` when Host matches public

The `POST /api/v1/portal/launch/{tool_id}` endpoint in `app/routers/portal.py`
has been updated so that when the incoming request's Host header matches
`*.deepaksharma.live`, the launch URL chooses `url_funnel` over
`url_external`. This keeps the chain consistent: a user clicking "Launch
Grafana" while on `https://deepaksharma.live` gets redirected to
`https://grafana.deepaksharma.live` — not `http://localhost:3000`, which is
meaningless from the public edge.

The internal-origin heuristic (`*.svc`, `*.local`, container names) still
takes priority so in-cluster callers hit the container port directly.

---

## Appendix C — Verification checklist (before you declare "done")

- [ ] `python -c "import yaml; d=yaml.safe_load(open('devops-tools-backend/config/tools.yaml')); print(sum(1 for t in d['tools'] if t.get('url_funnel')))"` prints 28 (NOTE: spec said 29, but
      34 total - 6 non-HTTP excluded = 28; the spec's arithmetic was off by one).
- [ ] `bash -n tailscale/bootstrap-tcp.sh` exits 0.
- [ ] `docker exec nginx-proxy nginx -t` is "test is successful".
- [ ] `tailscale funnel status` shows exactly ONE entry on :443.
- [ ] `curl -I https://deepaksharma.live/` returns 200 or 3xx.
- [ ] `curl -I https://grafana.deepaksharma.live/` returns 302 to `/login`.
- [ ] `openssl s_client ... | openssl x509 -noout -subject` shows `*.deepaksharma.live`.
- [ ] `htpasswd` is on the sensitive hostnames (see Phase F table).
- [ ] `certbot renew --dry-run` succeeds.

---

*Generated 2026-04-19. Updates to this doc should be committed alongside the
 corresponding config change; don't let it drift.*
