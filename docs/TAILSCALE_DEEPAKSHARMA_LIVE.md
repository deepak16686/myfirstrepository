# Runbook: Exposing the DevOps Portal via `deepaksharma.live` over Tailscale Funnel

Last reviewed: 2026-04-19

This runbook wires Deepak's custom domain `deepaksharma.live` through Tailscale
Funnel onto three concurrent public services — the DevOps Portal, Grafana,
and GitLab — while exposing every other tool in the 33-tool registry on
tailnet-only URLs (`https://<id>.deepak-desktop.tailac51e7.ts.net`).

> **Design constraint:** Tailscale Free caps Funnel at **3 concurrent
> services**. Our slot allocation:
>
> | Slot | Host                                | Purpose                                            |
> |------|-------------------------------------|----------------------------------------------------|
> | 1    | `deepaksharma.live`                 | Portal apex → nginx-proxy → frontend + `/api/*`    |
> | 2    | `grafana.deepaksharma.live`         | Grafana dashboards                                 |
> | 3    | `gitlab.deepaksharma.live`          | GitLab SCM/CI                                      |
>
> Everything else stays tailnet-only. Public users get the curated surface;
> tailnet-connected devices (Deepak's laptops / phone) get the full catalog.

Related files (all paths absolute, from repo root `C:/Users/deepak/ai-folder`):

- `C:/Users/deepak/ai-folder/tailscale/serve-config.json`
- `C:/Users/deepak/ai-folder/tailscale/bootstrap-funnel.sh`
- `C:/Users/deepak/ai-folder/nginx-proxy/portal.conf`
- `C:/Users/deepak/ai-folder/devops-tools-backend/config/tools.yaml`

---

## 1. Prerequisites

1. **Tailscale installed and logged in.**
   - Pick ONE location for tailscaled — Windows Tailscale app OR WSL
     (`curl -fsSL https://tailscale.com/install.sh | sh`) — **not both**. If
     you run both you'll get two tailnet nodes competing for cert issuance.
     Recommended: Windows Tailscale (menu bar) because it survives WSL
     restart and auto-starts at login.
2. **Tailscale admin console prerequisites** (https://login.tailscale.com/admin):
   - **DNS > MagicDNS**: enabled.
   - **DNS > HTTPS certificates**: enabled (issues LetsEncrypt cert for
     `*.deepak-desktop.tailac51e7.ts.net`).
   - **Access controls** (tailnet policy): Funnel node attribute granted to
     this machine:
     ```hujson
     "nodeAttrs": [
       {
         "target": ["deepak@"],
         "attr":   ["funnel"]
       }
     ]
     ```
   - **Settings > Feature previews**: Funnel is GA as of 2024-12, but the
     feature must still be toggled on per tailnet.
3. **Cap check**: no other node in the tailnet is currently holding Funnel
   slots. Confirm with `tailscale funnel status --json | jq 'keys'` on
   every tailnet node.
4. **Docker Desktop up** with the portal stack running and the three target
   ports published on the Windows host:
   - `localhost:8443` → nginx-proxy container
   - `localhost:3000` → grafana container
   - `localhost:8929` → gitlab-server container

## 2. DNS setup at the `deepaksharma.live` registrar

Custom domain -> tailnet MagicDNS name. You need both the wildcard and the
apex. Path A is the happy path (CNAME flattening / ALIAS). Path B is a
fallback for registrars that don't support apex CNAME.

### Path A — wildcard + flattened apex

| Type             | Name (subdomain) | Value                                    | TTL |
|------------------|------------------|------------------------------------------|-----|
| CNAME (wildcard) | `*`              | `deepak-desktop.tailac51e7.ts.net.`      | 300 |
| ALIAS / ANAME    | `@`              | `deepak-desktop.tailac51e7.ts.net.`      | 300 |

This works on Cloudflare (CNAME flattening, enabled by default on the free
tier), DNSimple, Netlify DNS, Route53 (ALIAS), NS1, etc.

### Path B — apex redirect (for registrars without ALIAS/flattening)

Set these instead:

| Type     | Name | Value                                    | TTL |
|----------|------|------------------------------------------|-----|
| CNAME    | `*`  | `deepak-desktop.tailac51e7.ts.net.`      | 300 |
| CNAME    | `www`| `deepak-desktop.tailac51e7.ts.net.`      | 300 |
| A / URL-forward | `@` | Registrar-side 301 redirect to `https://www.deepaksharma.live` | 300 |

Then access the portal at `https://www.deepaksharma.live` and add that host
to both the serve config and the nginx `server_name` line if you go this
route. Funnel slot still counts once per host:port.

Verify DNS with `dig +short deepaksharma.live` and
`dig +short grafana.deepaksharma.live` — both should return the MagicDNS
`ts.net` CNAME.

## 3. Bring up Tailscale on the host

**Decision — WSL vs Windows:** the runbook assumes Windows Tailscale. The
bootstrap script runs in WSL and talks to the Windows-side tailscaled via
`/mnt/c/Program Files/Tailscale/tailscale.exe` (the script auto-detects and
falls back). If you prefer to run tailscaled inside WSL, install the CLI
with `curl -fsSL https://tailscale.com/install.sh | sh`, then `sudo
tailscale up`, and make sure the Windows Tailscale app is fully quit.

```bash
# From Windows (PowerShell): tray icon -> Sign in... (browser flow)
# Verify:
"/mnt/c/Program Files/Tailscale/tailscale.exe" status
# Look for:   deepak-desktop    <your-ip>   active; direct
```

## 4. Apply the serve + funnel config

```bash
# WSL shell:
cd /mnt/c/Users/deepak/ai-folder
chmod +x tailscale/bootstrap-funnel.sh
./tailscale/bootstrap-funnel.sh
```

The script will:

1. Locate the Tailscale CLI (WSL install preferred; falls back to
   `/mnt/c/Program Files/Tailscale/tailscale.exe`).
2. Refuse to run if `tailscale status` shows the daemon isn't logged in.
3. Warn (non-fatal) if `tailscale cert deepak-desktop.tailac51e7.ts.net`
   can't issue — that means HTTPS isn't enabled in the admin console yet.
4. Apply `tailscale/serve-config.json` with
   `tailscale serve set-config <file>` (or
   `tailscale set --serve-config=<file>` on older CLIs).
5. Call `tailscale funnel --bg 443` as a belt-and-braces no-op (the
   `AllowFunnel` block in the config already opts in the three public hosts).
6. Run a smoke test with `curl -I -L` against each public URL and print the
   rollback command.

### What the config does, concretely

- **TLS listener**: tailscaled binds `:443` on the node and terminates TLS
  with the tailnet-issued LetsEncrypt cert.
- **SNI-based routing**: per-host entries in the `Web` block. Three hosts
  are flagged `AllowFunnel: true`; the rest are `false` (tailnet-only).
- **Proxy targets**: every host forwards to `127.0.0.1:<port>` on the
  Windows host. That port is the Docker Desktop published port; nginx-proxy
  listens on `:8443`, Grafana on `:3000`, GitLab on `:8929`.
- **nginx-proxy** then splits the portal slot apex traffic: `/api/*` →
  `devops-tools-backend:8003`, everything else → the Vite build served by
  `devops-tools-backend-frontend:80`.

## 5. Verification

```bash
# Public slots (run from anywhere on the open internet):
curl -I https://deepaksharma.live             # expect 200 (frontend landing)
curl -I https://deepaksharma.live/api/v1/portal/tools   # expect 200 (JSON)
curl -I https://grafana.deepaksharma.live                # expect 302 -> /login
curl -I https://gitlab.deepaksharma.live/-/readiness     # expect 200

# Tailnet-only (must be run from a device logged into the tailnet):
curl -I https://deepak-desktop.tailac51e7.ts.net/health         # expect 200
curl -I https://sonarqube.deepak-desktop.tailac51e7.ts.net/     # expect 200
curl -I https://vault.deepak-desktop.tailac51e7.ts.net/v1/sys/health   # 200 or 429

# Administrative inspection:
tailscale serve status    # shows the Web map
tailscale funnel status   # shows the 3 funnel entries + their backends
```

### Check the API reflects it

```bash
curl -s https://deepaksharma.live/api/v1/portal/tools \
  | jq '.[] | select(.url_funnel != null) | {id, url_funnel, url_tailnet}'
```

Expect three rows — `devops-tools-backend`, `devops-tools-frontend`,
`grafana`, and `gitlab`. (Backend + frontend share slot 1, so three
funnel slots, four registry rows.)

## 6. Troubleshooting

### 6.1 `tailscale cert` takes forever / 502 on first request

LetsEncrypt cert provisioning can take 30-120s the first time. Make a
single warm-up request with `curl -v https://deepak-desktop.tailac51e7.ts.net/`
and tailscaled will block until the cert is cached. After that, all three
funnel URLs will respond immediately. If it still hangs > 3 min:

- Admin console → DNS → "HTTPS certificates" must be enabled.
- The tailnet must not be using an overridden DNS setup that blocks
  LetsEncrypt's ACME challenges (the `acme-v02.api.letsencrypt.org` TXT
  resolver chain).

### 6.2 `cap of 3 services per tailnet reached`

Check which node is holding slots:

```bash
# Run on every known tailnet node:
tailscale funnel status --json
```

Any node with `AllowFunnel: true` on any host consumes a slot. Run
`tailscale funnel reset` on orphaned nodes, or upgrade the tailnet to a
paid plan.

### 6.3 MagicDNS cache / `NXDOMAIN` for `*.ts.net`

On the requesting device:

```bash
tailscale up --accept-dns=true        # make sure MagicDNS is on
tailscale netcheck                    # refresh DERP state
# Last-resort: restart tailscaled
sudo systemctl restart tailscaled     # Linux
# or: quit + relaunch the Windows tray app
```

### 6.4 Registrar hasn't propagated CNAME

```bash
dig +short @1.1.1.1 deepaksharma.live
dig +short @8.8.8.8 grafana.deepaksharma.live
```

Both must return `deepak-desktop.tailac51e7.ts.net.`. If only one returns,
it's a partial cache: wait up to the TTL or bump TTL lower and retry.

### 6.5 Funnel works but nginx returns 502 for `/`

nginx-proxy can't reach the upstream container. Inspect inside the network:

```bash
docker exec -it nginx-proxy sh -c 'wget -qO- http://devops-tools-backend-frontend:80/ | head -5'
docker exec -it nginx-proxy sh -c 'wget -qO- http://devops-tools-backend:8003/health'
```

If the first hostname doesn't resolve, your compose frontend container has
a different name — update the `upstream portal_frontend` block in
`nginx-proxy/portal.conf` and reload the container.

### 6.6 GitLab redirects to internal hostname

If `https://gitlab.deepaksharma.live` 302s to
`http://gitlab-server/users/sign_in`, set the `external_url` in GitLab's
`/etc/gitlab/gitlab.rb` inside the container:

```ruby
external_url 'https://gitlab.deepaksharma.live'
nginx['listen_https'] = false
nginx['listen_port']  = 80
nginx['proxy_set_headers'] = {
  "X-Forwarded-Proto" => "https",
  "X-Forwarded-Ssl"   => "on"
}
```

Then `gitlab-ctl reconfigure`.

### 6.7 Funnel disabled by admin

`admin/acls` must grant `"attr": ["funnel"]` to the tagged machine (or
directly to the `deepak@` user). If the bootstrap script reports
`funnel disabled for this tailnet`, open the admin console → Access
Controls and add the nodeAttr block shown in §1.

## 7. Rollback

### Soft rollback (keep tailscaled up, just close the public surface)

```bash
./tailscale/bootstrap-funnel.sh --reset
# or equivalently:
tailscale funnel reset
tailscale serve reset
```

Result: all 3 funnel entries disappear; every tailnet-only entry also
disappears (since they're all in the same declarative config). Portal is
no longer reachable over HTTPS from the internet OR the tailnet. Local
Docker Desktop ports (`localhost:*`) keep working.

### Revert the registry change only

If you just want to hide the funnel URLs from the portal UI without
touching tailscaled:

```bash
git checkout -- devops-tools-backend/config/tools.yaml
# The backend re-reads the YAML via mtime polling; no restart needed.
```

### Hard rollback (nuke tailscaled binding + logout)

```bash
tailscale funnel reset
tailscale serve  reset
tailscale down
# Optional — remove node from tailnet admin console:
# https://login.tailscale.com/admin/machines
```

### Notes on the nginx-proxy include

`nginx-proxy/portal.conf` is additive (new server blocks with scoped
`server_name`s). To back out:

1. `docker exec nginx-proxy rm /etc/nginx/conf.d/portal.conf`
2. `docker exec nginx-proxy nginx -s reload`

## 8. Tailscale CLI sources used for this runbook

Verified against current Tailscale docs on 2026-04-19:

- https://tailscale.com/docs/reference/tailscale-cli/serve
- https://tailscale.com/docs/reference/tailscale-cli/funnel
- https://tailscale.com/docs/features/tailscale-serve
- https://tailscale.com/docs/features/tailscale-funnel
- https://tailscale.com/kb/1247/funnel
- https://tailscale.com/kb/1242/tailscale-serve
- https://tailscale.com/kb/1313/serve-examples
- https://tailscale.com/kb/1589/tailscale-services-configuration-file
- Known round-trip bug with newer `"version": "0.0.1", "services": ...`
  format: https://github.com/tailscale/tailscale/issues/18381 — this is
  why we use the legacy `TCP` / `Web` / `AllowFunnel` schema here.
