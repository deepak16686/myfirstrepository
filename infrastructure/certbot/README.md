# certbot/ — Let's Encrypt wildcard cert automation for *.deepaksharma.live

Turnkey issuance and renewal of a wildcard TLS certificate
(`*.deepaksharma.live` + `deepaksharma.live` apex) via the DNS-01 challenge.
DNS-01 is mandatory for wildcards; HTTP-01 cannot issue `*` per the
[Let's Encrypt challenge reference](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge).

## Layout

```
certbot/
  README.md                     <-- you are here
  README-crontab.md             auto-renewal: Task Scheduler + WSL cron
  docker-compose.certbot.yml    Cloudflare DNS-01 (default)
  docker-compose.route53.yml    Route53 DNS-01 (fallback)
  issue-cert.sh                 one-shot issuance
  renew-cert.sh                 idempotent renewal (daily-safe)
  issue-cert-manual.sh          manual DNS path (any provider, no auto-renew)
  letsencrypt/                  cert state (persistent; gitignored)
  logs/                         renewal logs (gitignored)
  secrets/
    .gitignore                  deny-all for real creds
    cloudflare.ini.example      Cloudflare API-token template
    route53.env.example         AWS IAM credential template
```

Nothing under `letsencrypt/`, `logs/`, or `secrets/*.(ini|env|pem|key)` is
committed (repo root `.gitignore` + `certbot/secrets/.gitignore`).

Mirror target: `../nginx-proxy/certs/{fullchain,privkey}.pem` — this is the
source of truth that the nginx-proxy container mounts read-only at
`/etc/letsencrypt/live/deepaksharma.live/` (see §"nginx-proxy wiring" below).

## Quickstart — Cloudflare (default path)

**First run should always be staging** (untrusted but doesn't burn the
[5 identical certs / week rate limit](https://letsencrypt.org/docs/rate-limits/)).

```bash
# 1. Create the Cloudflare API token (see secrets/cloudflare.ini.example for
#    the exact scope — Zone.Zone:Read + Zone.DNS:Edit, on zone
#    deepaksharma.live ONLY).

# 2. Drop it into the ini file.
cp certbot/secrets/cloudflare.ini.example certbot/secrets/cloudflare.ini
$EDITOR certbot/secrets/cloudflare.ini     # paste the token, save
chmod 600 certbot/secrets/cloudflare.ini   # REQUIRED — script exits if broader

# 3. Staging dry-run first.
cd /c/Users/deepak/ai-folder
./certbot/issue-cert.sh --dry-run

# 4. If staging succeeded, do the real thing.
./certbot/issue-cert.sh

# 5. Verify the mirrored cert.
openssl x509 -in nginx-proxy/certs/fullchain.pem -noout -subject -issuer -dates
openssl x509 -in nginx-proxy/certs/fullchain.pem -noout -text \
    | grep -E 'Issuer|DNS:'
# Expected:
#   Issuer: C=US, O=Let's Encrypt, CN=R3
#   DNS:*.deepaksharma.live, DNS:deepaksharma.live

# 6. Bounce / reload nginx-proxy if it was running when step 4 completed.
docker exec nginx-proxy nginx -s reload
```

## Route53 fallback

```bash
cp certbot/secrets/route53.env.example certbot/secrets/route53.env
$EDITOR certbot/secrets/route53.env        # AWS_ACCESS_KEY_ID, etc.
chmod 600 certbot/secrets/route53.env
./certbot/issue-cert.sh --provider=route53 --dry-run    # staging
./certbot/issue-cert.sh --provider=route53              # prod
```

Minimum IAM policy for the scoped access key (substitute the real hosted
zone id, shown in the Route 53 console):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["route53:ListHostedZones", "route53:GetChange"],
      "Resource": ["*"]
    },
    {
      "Effect": "Allow",
      "Action": ["route53:ChangeResourceRecordSets"],
      "Resource": ["arn:aws:route53:::hostedzone/YOUR_HOSTED_ZONE_ID"]
    }
  ]
}
```

Reference: <https://certbot-dns-route53.readthedocs.io/en/stable/>

## Manual DNS path (any provider, no auto-renew)

Use when the provider has no certbot plugin (e.g. some registrar-owned DNS):

```bash
./certbot/issue-cert-manual.sh --dry-run    # staging
./certbot/issue-cert-manual.sh              # prod
```

Certbot pauses and prints **two** TXT records you must create manually (one
for the apex, one for the wildcard SAN). Wait ≥60 s for propagation; verify
with `dig +short TXT _acme-challenge.deepaksharma.live @8.8.8.8` before
pressing Enter. Only usable for first issuance — `certbot renew` on a
`--manual` lineage re-prompts every 60-90 days, so migrate to a plugin as
soon as you can.

## Auto-renewal

See [`README-crontab.md`](./README-crontab.md). TL;DR:

- **Windows Task Scheduler** (preferred): one PowerShell one-liner registers
  a daily task at 03:17 local.
- **WSL cron**: only if you keep WSL running 24/7.

Either way, `renew-cert.sh` is fully idempotent — runs that find >30 days
remaining exit 0 immediately without touching Let's Encrypt or nginx.

## nginx-proxy wiring

The nginx-proxy container expects certs at
`/etc/letsencrypt/live/deepaksharma.live/{fullchain,privkey}.pem`
([portal.conf lines 132-133](../nginx-proxy/portal.conf)).

Two mount strategies — pick one:

**Strategy A — mount the letsencrypt tree directly (prefers the real lineage)**

```yaml
volumes:
  - ../certbot/letsencrypt:/etc/letsencrypt:ro
```

Pros: zero copy step; certbot writes, nginx reads.
Cons: nginx container sees ALL lineages; slight blast radius if certbot
breaks the tree during renewal.

**Strategy B — mount the mirrored copy (recommended, and what our scripts
are wired for)**

```yaml
volumes:
  - ./nginx-proxy/certs:/etc/letsencrypt/live/deepaksharma.live:ro
```

Pros: nginx sees only the finalised pems; no symlink resolution, no chance
of reading a half-written file; works identically in Git Bash on Windows
where symlinks misbehave.
Cons: `issue-cert.sh` / `renew-cert.sh` must explicitly `cp` after issuance
(they do).

Our scripts implement Strategy B; see `devops-tools-backend/docker-compose.yml`
for the matching `nginx-proxy` service volume mount.

After any successful issuance or renewal the scripts run
`docker exec nginx-proxy nginx -s reload` (best-effort — warns but does not
fail if the container is down).

## DNS providers supported by certbot plugins

If you are NOT on Cloudflare or Route53, use one of the following official
plugins. Each has a Docker image at `certbot/dns-<name>:<tag>` on
[Docker Hub](https://hub.docker.com/u/certbot):

| Provider / plugin               | Docs URL                                                                                    |
| ------------------------------- | ------------------------------------------------------------------------------------------- |
| Cloudflare (default here)       | <https://certbot-dns-cloudflare.readthedocs.io/>                                            |
| AWS Route 53 (fallback here)    | <https://certbot-dns-route53.readthedocs.io/>                                               |
| Google Cloud DNS                | <https://certbot-dns-google.readthedocs.io/>                                                |
| DigitalOcean                    | <https://certbot-dns-digitalocean.readthedocs.io/>                                          |
| DNSimple                        | <https://certbot-dns-dnsimple.readthedocs.io/>                                              |
| DNS Made Easy                   | <https://certbot-dns-dnsmadeeasy.readthedocs.io/>                                           |
| Gehirn DNS                      | <https://certbot-dns-gehirn.readthedocs.io/>                                                |
| Linode                          | <https://certbot-dns-linode.readthedocs.io/>                                                |
| LuaDNS                          | <https://certbot-dns-luadns.readthedocs.io/>                                                |
| NS1                             | <https://certbot-dns-nsone.readthedocs.io/>                                                 |
| OVH                             | <https://certbot-dns-ovh.readthedocs.io/>                                                   |
| RFC 2136 (any dynamic-DNS zone) | <https://certbot-dns-rfc2136.readthedocs.io/>                                               |
| SakuraCloud                     | <https://certbot-dns-sakuracloud.readthedocs.io/>                                           |
| GoDaddy                         | third-party: <https://github.com/miigotu/certbot-dns-godaddy>                               |
| Namecheap                       | third-party: <https://github.com/knoxell/certbot-dns-namecheap>                             |
| Hetzner                         | third-party: <https://github.com/ctrlaltcoop/certbot-dns-hetzner>                           |
| ANY provider (manual TXT)       | built-in `--manual` mode (see `issue-cert-manual.sh`; does not auto-renew)                  |

To swap plugins, clone `docker-compose.certbot.yml`, change the image to
`certbot/dns-<plugin>:<tag>`, update the flags in the `command:`, and add a
credentials template under `secrets/`.

## Troubleshooting

### "DNS problem: NXDOMAIN looking up TXT for _acme-challenge..."

The authoritative nameserver hadn't seen the record yet when certbot
queried it. Causes:

1. Propagation too fast — bump `--dns-cloudflare-propagation-seconds` from
   60 to 120 in the compose file.
2. The wrong API token (e.g. one scoped to the wrong zone). Re-check the
   Cloudflare dashboard; the token must have **Zone:DNS:Edit** *on the
   exact zone* `deepaksharma.live`.
3. CAA record blocks Let's Encrypt. Check:
   `dig +short CAA deepaksharma.live @8.8.8.8`. If you have a CAA record,
   it MUST include `0 issue "letsencrypt.org"` or be absent entirely.
   [RFC 8659 reference](https://www.rfc-editor.org/rfc/rfc8659.html).

### "Too many certificates already issued for exact set of domains"

Duplicate-cert rate limit: **5 per week** per exact SAN set
(<https://letsencrypt.org/docs/rate-limits/>). Solutions:

- Use `--dry-run` (staging) while iterating.
- Wait until the 7-day rolling window expires.
- Temporarily add a dummy SAN like `-d dummy.deepaksharma.live` to bypass
  the duplicate check (burns 1 of the 50/week "new orders" limit).

### "Certbot does not know how to renew this certificate"

Usually means you issued with `--manual` and are now trying `renew`. Either
re-issue with a plugin path, or run `issue-cert-manual.sh` again.

### Staging vs prod

Let's Encrypt runs two CAs:

- Prod: `https://acme-v02.api.letsencrypt.org/directory` — rate-limited,
  returns browser-trusted certs. Default in our compose file.
- Staging: `https://acme-staging-v02.api.letsencrypt.org/directory` —
  generous limits, returns `(STAGING) Let's Encrypt` issuer (untrusted).

If `openssl x509 ... -issuer` shows `(STAGING)`, re-run without `--dry-run`.

### Propagation / dig sanity check

```bash
# Check the _acme-challenge TXT is live across public resolvers:
for ns in 1.1.1.1 8.8.8.8 9.9.9.9; do
    echo "-- $ns --"
    dig +short @"$ns" TXT _acme-challenge.deepaksharma.live
done
```

## Rollback

If a fresh cert is bad (wrong SANs, revoked, mis-wired) and you need to
fall back to the previous state:

1. **Stop using the bad cert**:
   ```bash
   # Swap the mirrored cert for the previous archive lineage.
   cp certbot/letsencrypt/archive/deepaksharma.live/fullchain<N-1>.pem \
      nginx-proxy/certs/fullchain.pem
   cp certbot/letsencrypt/archive/deepaksharma.live/privkey<N-1>.pem \
      nginx-proxy/certs/privkey.pem
   docker exec nginx-proxy nginx -s reload
   ```
   `<N-1>` = one less than the highest numbered `fullchain*.pem` in the
   archive directory.

2. **Revoke the bad cert** (if it was publicly issued):
   ```bash
   docker compose -f certbot/docker-compose.certbot.yml \
       --profile revoke run --rm \
       -v "$(pwd)/certbot/letsencrypt:/etc/letsencrypt" \
       certbot/dns-cloudflare:v2.11.0 \
       revoke \
       --cert-path /etc/letsencrypt/live/deepaksharma.live/fullchain.pem \
       --reason keycompromise \
       --non-interactive
   ```
   Revocation reason codes:
   <https://www.rfc-editor.org/rfc/rfc5280#section-5.3.1>.

3. **Remove the lineage from certbot's state** (optional, avoids confusing
   future `renew`):
   ```bash
   docker compose -f certbot/docker-compose.certbot.yml run --rm \
       --entrypoint certbot certbot \
       delete --cert-name deepaksharma.live --non-interactive
   ```

4. **Emergency fallback — self-signed cert** (2-minute brownout OK):
   ```bash
   mkdir -p nginx-proxy/certs
   openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
       -keyout nginx-proxy/certs/privkey.pem \
       -out nginx-proxy/certs/fullchain.pem \
       -subj "/CN=deepaksharma.live" \
       -addext "subjectAltName=DNS:deepaksharma.live,DNS:*.deepaksharma.live"
   docker exec nginx-proxy nginx -s reload
   ```
   Expect browser warnings until you re-issue a real cert.

## ADR reference

Architecture decision: we deliberately chose DNS-01 over HTTP-01 because:

- Only DNS-01 issues wildcards (<https://letsencrypt.org/docs/challenge-types/#dns-01-challenge>).
- The nginx-proxy is behind Tailscale Funnel in TCP-passthrough mode; we
  cannot answer an HTTP-01 challenge on `:80` without an additional L7 hop.
- DNS-01 works identically for every subdomain, so one cert covers all 33
  mapped tools (see `nginx-proxy/portal.conf`).

Architecture decision: we chose **Cloudflare scoped API tokens** over the
Global API Key because (a) least-privilege — the token can ONLY edit the
one zone's DNS — and (b) compromise radius — if the token leaks, it cannot
change billing, delete zones, or touch other properties on the account.

## Verify locally on docker-desktop

```bash
# 1. Build-time validation — no docker needed:
bash -n certbot/issue-cert.sh
bash -n certbot/renew-cert.sh
bash -n certbot/issue-cert-manual.sh
python -c "import yaml; yaml.safe_load(open('certbot/docker-compose.certbot.yml'))"
python -c "import yaml; yaml.safe_load(open('certbot/docker-compose.route53.yml'))"

# 2. Compose-level validation — needs docker:
docker compose -f certbot/docker-compose.certbot.yml config --quiet
docker compose -f certbot/docker-compose.route53.yml config --quiet

# 3. End-to-end staging run — needs a real Cloudflare API token:
./certbot/issue-cert.sh --dry-run
```
