# Cloudflare Tunnel for deepaksharma.live

This is the free no-VPS replacement for GoDaddy forwarding and Tailscale Funnel URLs in the browser.

## Why

GoDaddy forwarding is an HTTP redirect, so the browser address changes to `deepak-desktop.tailac51e7.ts.net`.
Cloudflare Tunnel is a reverse proxy: the browser stays on `https://deepaksharma.live`, while `cloudflared` makes an outbound-only tunnel from this machine to Cloudflare.

## Required one-time external setup

1. Create or open a free Cloudflare account.
2. Add `deepaksharma.live` as a Cloudflare website.
3. In the registrar account that actually owns `deepaksharma.live`, replace the current GoDaddy nameservers with the two Cloudflare nameservers Cloudflare gives you.
4. In Cloudflare Zero Trust, create a Cloudflare Tunnel named `deepaksharma-live`.
5. In the tunnel's Public Hostnames, add:

| Public hostname | Service type | Service URL | Extra setting |
|---|---|---|---|
| `deepaksharma.live` | HTTPS | `https://nginx-proxy:8443` | Disable TLS verification for origin |
| `*.deepaksharma.live` | HTTPS | `https://nginx-proxy:8443` | Disable TLS verification for origin |

The wildcard route lets the existing `nginx-proxy/portal.conf` host router keep handling subdomains such as `grafana.deepaksharma.live`, `chatbot.deepaksharma.live`, and `vault.deepaksharma.live`.

6. Copy the Docker connector token from Cloudflare and put it in `cloudflared/.env`:

```powershell
Copy-Item cloudflared\.env.example cloudflared\.env
notepad cloudflared\.env
```

## Run

```powershell
docker compose --env-file cloudflared\.env -f cloudflared\docker-compose.cloudflare-tunnel.yml up -d
```

## Verify

```powershell
docker logs cloudflared-deepaksharma-live --tail 50
Resolve-DnsName deepaksharma.live
curl.exe -I https://deepaksharma.live
```

The browser should remain on `https://deepaksharma.live` instead of redirecting to the Tailscale URL.

## Notes

- Do not keep GoDaddy forwarding enabled after Cloudflare DNS is active.
- Keep Tailscale Funnel as a fallback if you want, but public visitors should use the Cloudflare-backed domain.
- The current GoDaddy account checked in-browser did not contain `deepaksharma.live`; it only showed `deepaksharma.blog`. The nameserver change must be made from the account that owns `deepaksharma.live`.
