# GoDaddy DNS Setup — Wildcard TLS for `*.deepaksharma.live`

**Target state:** `https://portal.deepaksharma.live` (and every other `*.deepaksharma.live` subdomain) opens the locally hosted DevOps Portal, served with a browser-trusted Let's Encrypt wildcard certificate. The portal is already publicly reachable at `https://deepak-desktop.tailac51e7.ts.net/` via Tailscale Funnel — this runbook adds the branded domain on top of that working baseline.

**Updated:** 2026-04-20. Maintainer: `deepakdce2009@gmail.com`.

---

## 1. Decision table — pick a path before you touch GoDaddy

| Path | Automation | Renewal touch | Apex (`deepaksharma.live`) | Cost | Recommendation |
|------|------------|---------------|-----------------------------|------|----------------|
| **A. Cloudflare delegation** (change GoDaddy NS → Cloudflare free tier, use `certbot-dns-cloudflare`) | Full (cron/scheduler) | Zero — renews silently every 60 days | Works via Cloudflare CNAME-flattening | Free | **Recommended.** One-time 30-min setup; zero ongoing operator time. |
| **B. GoDaddy community plugin** (`certbot-dns-godaddy`, already scaffolded) | Full, **if API works** | Zero if API works | GoDaddy disallows CNAME at apex — use HTTP Forwarding or subdomain only | Free | Second choice. Likely blocked — GoDaddy's DNS API silently gates accounts with <10 domains. Expect `HTTP 403 UNABLE_TO_AUTHENTICATE`. |
| **C. Manual DNS-01** (interactive TXT record via GoDaddy UI) | Issue only | **Every 60 days you copy/paste two TXT records by hand** | Same apex limits as B | Free | Works today with zero prerequisites. Fine as a bridge until you move to path A. |
| **D. AWS Route53** (delegate zone to Route53) | Full | Zero | Route53 supports alias records at apex | ~$0.50/month/zone | Only if you already use AWS. No new account worth creating just for this. |

> **Caveat up front (affects paths B and C both):** GoDaddy does **not** support CNAME at the zone apex (`@`). This is not a bug — it's a standards quirk (RFC 1912 §2.4 forbids CNAME coexisting with SOA/NS) that only some providers work around via flattening. For `*.deepaksharma.live` subdomains this is fine. For the bare apex `https://deepaksharma.live/` you have three options, covered in section 3.

---

## 2. Mandatory DNS records (apply to **all** paths)

Login URL: [https://dcc.godaddy.com/manage/deepaksharma.live/dns](https://dcc.godaddy.com/manage/deepaksharma.live/dns)

Add the following records (TTL 600 = 10 minutes, low enough to iterate without multi-hour propagation waits):

| Type  | Name  | Value                                     | TTL | Purpose                                                        |
|-------|-------|-------------------------------------------|-----|----------------------------------------------------------------|
| CNAME | `*`   | `deepak-desktop.tailac51e7.ts.net.`       | 600 | Wildcard — routes every subdomain to the Tailscale Funnel node |
| CNAME | `www` | `deepak-desktop.tailac51e7.ts.net.`       | 600 | Apex-like access via `www.deepaksharma.live`                   |

> **Note:** include the trailing dot in the value (`...ts.net.`). Some GoDaddy UI versions quietly trim it, some don't. Either form resolves the same way — the record is authoritative on the zone regardless.

Verify from any machine after ~5–10 minutes (TTL + propagation slack):

```bash
dig +short portal.deepaksharma.live CNAME
# expect: deepak-desktop.tailac51e7.ts.net.

dig +short www.deepaksharma.live CNAME
# expect: deepak-desktop.tailac51e7.ts.net.

# Resolve the funnel node's A record to prove end-to-end:
dig +short deepak-desktop.tailac51e7.ts.net A
# expect: a public IPv4 owned by Tailscale (100.100.100.x NOT correct — that's the internal CGNAT; public A is different)
```

If `dig` returns no answer, wait one more TTL cycle then re-check. Do not re-add the record — GoDaddy's UI doesn't de-dupe and you'll end up with two conflicting RRsets.

---

## 3. Apex (`https://deepaksharma.live/`) — three options

Because GoDaddy doesn't CNAME-flatten, choose ONE:

### 3a. Accept the limitation (simplest)

Do nothing extra. Users hit `https://portal.deepaksharma.live/` directly. Bare apex resolves to NXDOMAIN / nothing. Perfectly reasonable for a personal / internal tool portal.

### 3b. GoDaddy HTTP Forwarding (no code change)

1. Open [https://dcc.godaddy.com/control/portfolio/deepaksharma.live/settings](https://dcc.godaddy.com/control/portfolio/deepaksharma.live/settings).
2. Locate **Forwarding** → **Add Forwarding**.
3. Source: `https://deepaksharma.live` (apex only, leave `www.` out — we already CNAMEd `www` above).
4. Destination: `https://portal.deepaksharma.live/`.
5. Forward type: **Permanent (301)**.
6. Settings: **Forward only** (NOT "Masking" — masking uses an iframe that breaks the portal's CSP and modern browser SameSite cookies).
7. Save. GoDaddy provisions A + AAAA records at the apex pointing at their parking/redirect infra; propagation takes ~1 hour.

> **Note:** GoDaddy's HTTP Forwarding serves the apex with a GoDaddy-owned IP and a GoDaddy-owned cert. Users see one 301 hop in devtools — cosmetically fine, functionally equivalent. If you want apex served from your own node, use path A (Cloudflare) instead.

### 3c. Delegate to Cloudflare (permanent fix — this is Path A)

Cloudflare flattens CNAMEs at apex for free on every plan. See section 5.

---

## 4. Path B — GoDaddy community plugin

The scaffolding already exists. This is the "if their API lets you through, it just works" path.

### Prerequisites

- GoDaddy account with the domain registered.
- 2FA enabled on the GoDaddy account (see Security appendix §10).
- Docker Desktop running (WSL2 integration on).
- DNS records from section 2 already added.

### Step-by-step

```bash
# 1. Visit https://developer.godaddy.com/keys
#    -> Create New API Key
#    -> Name:        certbot-dns-godaddy-deepaksharma-live
#    -> Environment: Production   (NOT "OTE" — OTE keys don't affect live DNS)
#    -> Copy Key and Secret; Secret is shown ONCE only.

# 2. Copy the template, fill in key + secret, lock it down.
cd /c/Users/deepak/ai-folder
cp certbot/secrets/godaddy.ini.example certbot/secrets/godaddy.ini
# Open in your editor, replace REPLACE_WITH_GODADDY_API_KEY / SECRET placeholders.
# Then lock perms — issue-cert.sh REFUSES to run if file perms are broader than 600.
chmod 600 certbot/secrets/godaddy.ini

# 3. Verify the Dockerfile's plugin install succeeds (build is cached after first run).
docker compose -f certbot/docker-compose.godaddy.yml build certbot-godaddy

# 4. STAGING dry-run first — Let's Encrypt's prod has a 5/week duplicate-cert
#    rate limit. Staging has generous limits but issues an UNTRUSTED cert.
bash certbot/issue-cert.sh --provider=godaddy --dry-run

# 5. If step 4 succeeded (look for "Successfully received certificate" near the
#    end of the docker output), run PRODUCTION issuance:
bash certbot/issue-cert.sh --provider=godaddy

# 6. Cert lands at certbot/letsencrypt/live/deepaksharma.live/{fullchain,privkey}.pem
#    and is mirrored to nginx-proxy/certs/ by issue-cert.sh automatically.
```

### Critical failure mode — detection

If the plugin returns this error, your account is gated out of the DNS API:

```
HTTP 403
{"code": "UNABLE_TO_AUTHENTICATE", "message": "Unable to authenticate user"}
```

**Meaning:** the key+secret are valid (`HTTP 401` would be an invalid key). GoDaddy's backend refuses API access based on account-tier rules. As of early 2026 they gate on:

- Fewer than 10 active domains on the account, **OR**
- Account is not on a "Domains Plus" / Discount Domain Club plan.

Your account has one domain and is on the standard plan, so you will very likely hit this. **Do not burn cycles debugging the plugin, the keys, or the credentials file — it's them, not you.**

Confirm by curling the API directly:

```bash
# Replace KEY and SECRET with your production values (do NOT commit)
curl -sS -i -H "Authorization: sso-key KEY:SECRET" \
  https://api.godaddy.com/v1/domains/deepaksharma.live/records/TXT \
  | head -5

# HTTP/2 403                            <-- gated; UI-only account, fall back to Path C or A
# HTTP/2 200                            <-- gold, proceed with the plugin
# HTTP/2 401                            <-- key typo; re-check godaddy.ini
```

Pivot to path A (recommended) or path C (quick fix) on 403.

### Renewal (path B)

`certbot/renew-cert.sh` supports `--provider=godaddy` by the same compose file. Schedule once, forget:

**Windows (Task Scheduler):**

```powershell
# Run daily at 03:15; certbot internally skips if lineage >30 days from expiry.
schtasks /Create /SC DAILY /ST 03:15 /TN "certbot-renew-deepaksharma" /TR ^
  "bash.exe -lc 'cd /c/Users/deepak/ai-folder && ./certbot/renew-cert.sh --provider=godaddy'"
```

**WSL cron:**

```bash
crontab -e
# Add:
15 3 * * * cd /c/Users/deepak/ai-folder && ./certbot/renew-cert.sh --provider=godaddy >> certbot/logs/cron.log 2>&1
```

### Rollback (path B)

```bash
# Disable auto-renew
schtasks /Delete /TN "certbot-renew-deepaksharma" /F    # Windows
# OR remove the crontab line in WSL

# Revoke the issued cert (invalidates the wildcard at the CT log level):
docker compose -f certbot/docker-compose.certbot.yml --profile revoke run --rm \
  certbot-revoke \
  revoke --cert-path /etc/letsencrypt/live/deepaksharma.live/fullchain.pem \
  --reason keycompromise --non-interactive

# Wipe local cert state:
rm -rf certbot/letsencrypt/live/deepaksharma.live*
rm -rf certbot/letsencrypt/archive/deepaksharma.live*
rm -rf certbot/letsencrypt/renewal/deepaksharma.live*.conf

# Restore the self-signed placeholder so nginx-proxy doesn't hard-fail:
openssl req -x509 -nodes -days 30 -newkey rsa:2048 \
  -keyout nginx-proxy/certs/privkey.pem \
  -out nginx-proxy/certs/fullchain.pem \
  -subj "/CN=deepaksharma.live" \
  -addext "subjectAltName=DNS:deepaksharma.live,DNS:*.deepaksharma.live"
docker exec nginx-proxy nginx -s reload
```

---

## 5. Path A — Cloudflare delegation (RECOMMENDED)

Pay one-time cost: change nameservers at GoDaddy, wait ~30 min for propagation. Ongoing cost: zero — the `certbot-dns-cloudflare` plugin is first-party to certbot and never gates tokens. Apex (`deepaksharma.live/`) also works thanks to Cloudflare's CNAME flattening.

### Prerequisites

- Cloudflare account (free tier is fine). Sign up at [https://dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up).
- Access to the GoDaddy nameserver control panel.

### Step-by-step

```bash
# 1. Add the site to Cloudflare.
#    Dashboard -> "Add a Site" -> enter "deepaksharma.live" -> pick the Free plan.
#    Cloudflare scans your existing records; it will auto-create any A/CNAME/TXT/MX
#    it finds. Review the list. Re-add any records the scan misses (Cloudflare
#    has no way to see GoDaddy's parking-forwarding records, for example).

# 2. Cloudflare presents two nameservers, e.g.
#      <adjective1>.ns.cloudflare.com
#      <adjective2>.ns.cloudflare.com
#    (The exact names vary per account — look in the dashboard.)

# 3. In GoDaddy: https://dcc.godaddy.com/manage/deepaksharma.live/dns
#    -> "Nameservers" section (bottom of page)
#    -> "Change Nameservers" -> "Enter my own nameservers (advanced)"
#    -> paste the two Cloudflare nameservers -> Save
#    GoDaddy warns about propagation; click through.

# 4. Wait for delegation to propagate. Test:
dig +short NS deepaksharma.live
# expect: both cloudflare nameservers
# if still returning GoDaddy's ns (.domaincontrol.com), wait longer. Typically 30 min, can be up to 24h for first delegation.

# 5. In the Cloudflare dashboard, once propagation completes, the dashboard
#    shows "Active" for the zone. You can now add the two CNAMEs from section 2.
#    (Records you added to GoDaddy post-delegation are NOT picked up — the
#    authoritative source is now Cloudflare.)
#
#    Cloudflare UI: DNS -> Records -> Add Record
#      Type: CNAME  Name: *     Target: deepak-desktop.tailac51e7.ts.net  Proxy: DNS only (grey cloud)  TTL: Auto
#      Type: CNAME  Name: www   Target: deepak-desktop.tailac51e7.ts.net  Proxy: DNS only (grey cloud)  TTL: Auto
#      Type: CNAME  Name: @     Target: deepak-desktop.tailac51e7.ts.net  Proxy: DNS only (grey cloud)  TTL: Auto  <-- works because CF flattens
#
#    IMPORTANT: keep Proxy = "DNS only" (grey cloud). The orange cloud (proxy
#    mode) would MITM-terminate TLS at Cloudflare and break Tailscale Funnel's
#    end-to-end TCP passthrough for the wildcard cert.

# 6. Create a scoped Cloudflare API token.
#    https://dash.cloudflare.com/profile/api-tokens -> Create Token -> Create Custom Token
#      Name:         certbot-deepaksharma-live
#      Permissions:  Zone | Zone | Read
#                    Zone | DNS  | Edit
#      Zone Resources: Include | Specific zone | deepaksharma.live
#      TTL: 1 year (set a calendar reminder to rotate)
#    Copy the token (shown ONCE).

# 7. Drop the token in the already-scaffolded credentials file.
cd /c/Users/deepak/ai-folder
cp certbot/secrets/cloudflare.ini.example certbot/secrets/cloudflare.ini
# Edit: replace REPLACE_WITH_SCOPED_TOKEN with the real token.
chmod 600 certbot/secrets/cloudflare.ini

# 8. Run issuance. Staging first, then prod.
bash certbot/issue-cert.sh --dry-run
bash certbot/issue-cert.sh
```

> **Note:** the repo's `certbot/docker-compose.certbot.yml` pins `certbot/dns-cloudflare:v2.11.0` with digest `sha256:6fda5efe1140c256dd01ac5823731423c41914eb5962dd44e01cdd33bf7a0fa6`. That image is vendor-maintained by EFF (certbot team), not a third-party; treat it as trusted.

### Renewal (path A)

Same as path B but with `--provider=cloudflare` (the default — flag can be omitted):

```bash
# Windows Task Scheduler
schtasks /Create /SC DAILY /ST 03:15 /TN "certbot-renew-deepaksharma" /TR ^
  "bash.exe -lc 'cd /c/Users/deepak/ai-folder && ./certbot/renew-cert.sh'"

# WSL cron
15 3 * * * cd /c/Users/deepak/ai-folder && ./certbot/renew-cert.sh >> certbot/logs/cron.log 2>&1
```

### Rollback (path A)

Rolling back the cert portion is the same procedure as Path B's rollback — the cert lineage name is `deepaksharma.live` either way (certbot doesn't encode the DNS provider in the lineage).

To roll back the nameserver delegation itself:

1. GoDaddy: DNS panel -> Nameservers -> "Change Nameservers" -> "Use GoDaddy defaults" -> Save.
2. Propagation takes 30 min to 24h.
3. All records you created in Cloudflare stop being authoritative. Re-create them in GoDaddy's UI.

---

## 6. Path C — manual DNS-01 (works today, no API needed)

Use this when paths A and B both need work you don't want to do right now. The trade-off is that you must repeat the manual TXT-record dance every 60 days when the cert renews.

### Prerequisites

- GoDaddy account with UI access.
- DNS records from section 2 already added.
- Docker Desktop running.

### Step-by-step

```bash
cd /c/Users/deepak/ai-folder

# 1. Dry-run against Let's Encrypt staging first (untrusted cert, no rate-limit burn)
bash certbot/issue-cert-manual.sh --dry-run

# 2. Certbot will PAUSE and print something like:
#
#    Please deploy a DNS TXT record under the name:
#      _acme-challenge.deepaksharma.live
#    with the following value:
#      abcDEF123xyz...
#    (Note: this value is different each run, and there will be TWO records
#    in sequence — one for the wildcard SAN, one for the apex SAN.)

# 3. Go to https://dcc.godaddy.com/manage/deepaksharma.live/dns
#    -> Add Record
#    -> Type: TXT
#    -> Name:  _acme-challenge
#       (GoDaddy auto-appends .deepaksharma.live, which is correct)
#    -> Value: paste the EXACT string certbot printed. No quotes. No trailing spaces.
#    -> TTL:   600 (so subsequent renewals don't wait for yesterday's cached record)
#    -> Save

# 4. Verify propagation from a public resolver before hitting Enter:
dig +short TXT _acme-challenge.deepaksharma.live @8.8.8.8
dig +short TXT _acme-challenge.deepaksharma.live @1.1.1.1
# expect: both to return the value you pasted. If one returns empty, wait
# another 30 seconds and re-check. GoDaddy propagates within ~1-2 minutes
# at TTL 600.

# 5. Press Enter in the certbot prompt.

# 6. Certbot prompts a SECOND time with a new TXT value for the apex SAN.
#    You have two choices:
#    (a) Edit the existing _acme-challenge record and REPLACE the value — the
#        Let's Encrypt validator checks the TXT RRset as a whole and accepts
#        either one of multiple values present.
#    (b) CREATE a second TXT record with the same Name (_acme-challenge) and
#        the new value — GoDaddy supports multiple TXTs at the same name.
#    Option (b) is safer — don't delete a value that might still be validating.

# 7. Wait for propagation, press Enter again, and certbot finishes:
#    "Successfully received certificate."
#    Lineage lands at certbot/letsencrypt/live/deepaksharma.live-staging/ (dry-run)
#    or certbot/letsencrypt/live/deepaksharma.live/ (prod).

# 8. If the dry-run succeeded, run the production version:
bash certbot/issue-cert-manual.sh

# 9. AFTER prod issuance completes: clean up the TXT records from GoDaddy's UI
#    (leaving them around is fine but cluttered; Let's Encrypt will not re-check
#    them until renewal 60 days from now).
```

### Renewal (path C) — the painful part

Every ~60 days, certbot's renew will fail non-interactively with:

```
The manual plugin is not working; there may be problems with your existing configuration.
...
The requested authenticator manual is not usable
```

Because `renew` runs non-interactively by default and the `--manual` authenticator cannot be non-interactive. You have to re-run `issue-cert-manual.sh` manually:

```bash
# Set a calendar reminder for day 75 of the cert's life (15-day safety margin):
# "Renew deepaksharma.live wildcard — see docs/GODADDY_DNS_SETUP.md §6"

bash certbot/issue-cert-manual.sh   # re-do the TXT dance
```

> **Note:** this is why path A is recommended. If you end up on path C, put a repeating 60-day calendar reminder RIGHT NOW. Let's Encrypt certs expire at day 90; browser trust fails hard on day 91.

### Rollback (path C)

Same cert-rollback steps as path B. Additionally, delete any leftover `_acme-challenge` TXT records from GoDaddy's UI (they are public and, while not sensitive, are debris).

---

## 7. Path D — AWS Route53 (mentioned for completeness)

Only attractive if you **already** have an AWS account and don't want to add a Cloudflare one.

**Cost:** $0.50/month per hosted zone + $0.40 per million queries (negligible for this use case; first 25 billion queries/month on a single zone cost ~$10/year in practice).

**Setup outline** (not full walk-through — see the AWS docs if this is your pick):

1. AWS Console → Route53 → "Create hosted zone" → `deepaksharma.live`.
2. Record the four `ns-XX.awsdns-XX.com` / `.net` / `.org` / `.co.uk` nameservers.
3. At GoDaddy: Nameservers → Change → paste all four AWS NS records → Save. Wait 30 min.
4. Route53 → create record: `*.deepaksharma.live` CNAME → `deepak-desktop.tailac51e7.ts.net`.
5. Create IAM user `certbot-dns-route53` with inline policy allowing `route53:ListHostedZones`, `route53:GetChange`, and `route53:ChangeResourceRecordSets` on that zone ARN only.
6. Put the access key + secret in `certbot/secrets/route53.env` (template exists at `certbot/secrets/route53.env.example`).
7. Run `bash certbot/issue-cert.sh --provider=route53 --dry-run`, then prod.

Repo already ships `certbot/docker-compose.route53.yml` and `issue-cert.sh --provider=route53` wiring, so the mechanics are identical to path A/B once credentials are in place.

Renewal and rollback steps are the same shape as path A.

---

## 8. Flip the Tailscale Funnel to TCP passthrough (all paths converge here)

Once the cert is issued and mirrored to `nginx-proxy/certs/`, switch the Tailscale Funnel from its current HTTPS-terminating mode (`:443 → http://127.0.0.1:8003`, portal only) to TCP passthrough mode (`:443 → 127.0.0.1:8443`, nginx-proxy + SNI routing to all 28 tools).

```bash
cd /c/Users/deepak/ai-folder

# 1. Tear down the current single-slot HTTPS funnel.
tailscale funnel --https=443 off
tailscale serve reset

# 2. Apply the TCP-passthrough config. bootstrap-tcp.sh checks for the wildcard
#    cert at /etc/letsencrypt/live/deepaksharma.live/ before committing — if it
#    can't find it, it WARNs but continues (you can override CERT_DIR=... if
#    your cert lives elsewhere).
bash tailscale/bootstrap-tcp.sh --apply

# 3. The script runs its own smoke test at the end (curls a few SMOKE_HOSTS).
#    Expect HTTP 200 / 302 / 401 depending on the tool — NOT 502 or ssl errors.
```

### Verification

```bash
# Portal root — should return the built SPA's index.html referencing hashed assets
curl -sS https://portal.deepaksharma.live/ | grep -oE 'src="[^"]*"' | head -3
# expect: src="/assets/index-<hash>.js"

# Per-tool: basic-auth gated tools 401 without creds
curl -sS -o /dev/null -w "%{http_code}\n" https://ollama.deepaksharma.live/
# expect: 401

# Per-tool: basic-auth gated tools 200 with seeded bcrypt creds
curl -sS -u "$TOOL_USER:$TOOL_PASS" -o /dev/null -w "%{http_code}\n" \
  https://ollama.deepaksharma.live/
# expect: 200

# Own-login tool, no gate
curl -sS -o /dev/null -w "%{http_code}\n" https://grafana.deepaksharma.live/
# expect: 200 (or 302 to /login)

# Cert check — should be Let's Encrypt, not your self-signed placeholder
openssl s_client -servername portal.deepaksharma.live \
  -connect portal.deepaksharma.live:443 </dev/null 2>/dev/null \
  | openssl x509 -noout -issuer -subject -dates
# issuer=C=US, O=Let's Encrypt, CN=R3 (or E1/E5/R11 depending on LE's current intermediate)
# subject=CN=deepaksharma.live
# notAfter=~90 days from issuance
```

---

## 9. Rollback (revert to current "MagicDNS-only" working state)

If any step of section 8 breaks and you want the pre-branded baseline back:

```bash
# 1. Clear the TCP funnel config:
tailscale serve reset

# 2. Restore the current HTTPS-terminating funnel that routes straight at the portal:
tailscale funnel --bg --https=443 http://127.0.0.1:8003

# 3. Public URL returns to:
#    https://deepak-desktop.tailac51e7.ts.net/
#    (the branded *.deepaksharma.live URLs stop resolving — DNS still points at
#    the funnel, but the funnel no longer does TCP passthrough so nginx-proxy
#    isn't reached).

# 4. (Optional) Restore the self-signed placeholder in nginx-proxy/certs/ if
#    you've lost trust in the issued cert:
openssl req -x509 -nodes -days 30 -newkey rsa:2048 \
  -keyout nginx-proxy/certs/privkey.pem \
  -out nginx-proxy/certs/fullchain.pem \
  -subj "/CN=deepaksharma.live" \
  -addext "subjectAltName=DNS:deepaksharma.live,DNS:*.deepaksharma.live"
docker exec nginx-proxy nginx -s reload
```

Verify:

```bash
curl -sS -o /dev/null -w "%{http_code}\n" https://deepak-desktop.tailac51e7.ts.net/
# expect: 200 (same as before this whole exercise)
```

---

## 10. Security appendix

### Credential storage

| File                                    | Contents                           | Perms | Gitignore scope                              |
|-----------------------------------------|------------------------------------|-------|----------------------------------------------|
| `certbot/secrets/godaddy.ini`           | GoDaddy API key + secret           | 600   | `certbot/secrets/.gitignore` denies `*.ini`  |
| `certbot/secrets/cloudflare.ini`        | Cloudflare scoped API token        | 600   | Same                                         |
| `certbot/secrets/route53.env`           | AWS access key ID + secret         | 600   | `certbot/secrets/.gitignore` denies `*.env`  |
| `certbot/letsencrypt/live/*/privkey.pem`| Private key for the wildcard cert  | 600   | `certbot/letsencrypt/` is entirely gitignored|
| `nginx-proxy/certs/privkey.pem`         | Mirrored copy of the above         | 600   | `nginx-proxy/certs/.gitignore` denies `*.pem`|

`issue-cert.sh` verifies `0600` or `0400` on the credential file and refuses to run if perms are broader — don't work around that check.

### What NOT to commit

- Any `*.ini` file (Cloudflare, GoDaddy credentials). `cloudflare.ini.example` / `godaddy.ini.example` are the only safe `.ini` files in the repo.
- Any `*.env` file with real values. `route53.env.example` is the template; never commit the real one.
- Any `*.pem` file in `nginx-proxy/certs/` or `certbot/letsencrypt/`. The self-signed placeholder currently in `nginx-proxy/certs/` was committed before this policy; it will be overwritten and then only tracked in `.gitignore`.
- Any `*.key` file, regardless of location.

Verify before pushing with:

```bash
git status --porcelain | grep -iE '\.(ini|env|pem|key)$'
# expect: only *.example files, never bare ones
```

### Password handling

If you paste a GoDaddy account password, API key, Cloudflare token, or AWS secret into a chat window or terminal that sends output anywhere: **rotate it immediately**. Keys in chat transcripts and terminal scrollbacks are compromised from the moment they leave the generating page.

- GoDaddy API keys: revoke at [https://developer.godaddy.com/keys](https://developer.godaddy.com/keys) → Delete → regenerate.
- Cloudflare API tokens: revoke at [https://dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens) → ... → Delete → regenerate with the same scope.
- AWS access keys: IAM Console → Users → `certbot-dns-route53` → Security credentials → Make inactive → Delete → Create new.
- GoDaddy account password: login portal → Security → Change password. Also rotate 2FA if the password was leaked together with a 2FA recovery code.

### API key scope requirements

| Provider   | Minimum scope                                                                 | Over-scoped form to AVOID                              |
|------------|-------------------------------------------------------------------------------|--------------------------------------------------------|
| GoDaddy    | Production environment, DNS read + write (account-global — cannot be scoped)  | OTE environment (keys don't affect live DNS)           |
| Cloudflare | `Zone:Zone:Read` + `Zone:DNS:Edit`, **Specific zone = deepaksharma.live only**| Global API Key (full account, non-revocable individually) |
| AWS        | `route53:ListHostedZones` + `route53:GetChange` + `route53:ChangeResourceRecordSets` on the one zone ARN | AdministratorAccess, `route53:*` on `Resource: "*"` |

### 2FA

- **GoDaddy:** Settings → Login & PIN → Two-Step Verification → enable TOTP (authenticator app). Avoid SMS — SIM-swap attacks on domain registrars are a known playbook.
- **Cloudflare:** Profile → Authentication → Two-Factor Authentication → TOTP.
- **AWS root account:** Security credentials → Activate MFA → Virtual MFA device. (Plus: create an IAM user for day-to-day, stop using root.)

---

## 11. Cross-links

All paths referenced here exist in the repo:

| Path                                          | Purpose                                                          |
|-----------------------------------------------|------------------------------------------------------------------|
| `certbot/Dockerfile.godaddy`                  | Builds `local/certbot-dns-godaddy:2.11.0` with the community plugin baked in. |
| `certbot/docker-compose.godaddy.yml`          | Four services: `certbot-godaddy` (prod issue), `certbot-godaddy-staging` (dry-run), `certbot-godaddy-renew` (idempotent renew). |
| `certbot/docker-compose.certbot.yml`          | Same four services but for Cloudflare (path A). |
| `certbot/docker-compose.route53.yml`          | Same four services but for Route53 (path D). |
| `certbot/secrets/godaddy.ini.example`         | Template for GoDaddy key + secret; documents the `UNABLE_TO_AUTHENTICATE` caveat inline. |
| `certbot/secrets/cloudflare.ini.example`      | Template for Cloudflare scoped API token; documents token creation at [cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens). |
| `certbot/secrets/route53.env.example`         | Template for AWS access key ID + secret. |
| `certbot/issue-cert.sh`                       | Orchestrator. Accepts `--provider=cloudflare|route53|godaddy` and `--dry-run`. Pre-flights credentials, runs certbot, mirrors to `nginx-proxy/certs/`, reloads the container. |
| `certbot/issue-cert-manual.sh`                | Interactive DNS-01 path — no plugin needed. Prints TXT records, waits for Enter, verifies propagation. |
| `certbot/renew-cert.sh`                       | Idempotent renewal. Safe to run daily from cron / Task Scheduler. Exits 0 if lineage >30 days from expiry. |
| `certbot/README.md`                           | Umbrella doc for the certbot directory (complements this file). |
| `certbot/README-crontab.md`                   | Cron / scheduled-task snippets for all three provider paths. |
| `tailscale/bootstrap-tcp.sh`                  | Flips funnel to TCP passthrough. `--apply` / `--status` / `--reset`. |
| `tailscale/bootstrap-funnel.sh`               | Old 3-slot HTTPS design; kept on disk for rollback but superseded by `bootstrap-tcp.sh`. |
| `tailscale/serve-config.json`                 | huJSON template for the TCP passthrough config, `${MAGIC_DNS_NAME}` substituted at apply time. |
| `nginx-proxy/portal.conf`                     | SNI router on `:8443`; maps each `*.deepaksharma.live` to a container:port upstream. Basic-auth gate for 11 raw-data tools. |
| `docs/PUBLIC_REACHABILITY_STATUS.md`          | Current 28/28-tools-locally-reachable state; explains what remains before public reachability. |
| `docs/TAILSCALE_DEEPAKSHARMA_LIVE.md`         | Original design doc for the Tailscale Funnel approach. |
| `docs/PUBLIC_ACCESS_DEEPAKSHARMA_LIVE.md`     | Long-form architecture rationale for the public-access design. |

---

## 12. What happens next — exact commands in order

After you pick a path and DNS is live + the cert is issued + mirrored to `nginx-proxy/certs/`, run these in sequence from `C:\Users\deepak\ai-folder` in Git Bash:

```bash
# 1. Verify DNS resolves from the public internet (not just from your machine):
dig +short portal.deepaksharma.live CNAME @8.8.8.8
# expect: deepak-desktop.tailac51e7.ts.net.

# 2. Verify cert is on disk at the expected path:
ls -la certbot/letsencrypt/live/deepaksharma.live/
# expect: fullchain.pem, privkey.pem, chain.pem, cert.pem (all symlinks into ../archive/)

# 3. Verify the cert is actually the wildcard LE cert, not the self-signed placeholder:
openssl x509 -in nginx-proxy/certs/fullchain.pem -noout -issuer -subject \
  -ext subjectAltName
# expect:
#   issuer=C=US, O=Let's Encrypt, CN=R3  (or E1/E5/R11)
#   subject=CN=deepaksharma.live
#   X509v3 Subject Alternative Name:
#       DNS:*.deepaksharma.live, DNS:deepaksharma.live

# 4. Reload nginx-proxy to pick up the new cert (issue-cert.sh does this too, but idempotent):
docker exec nginx-proxy nginx -t && docker exec nginx-proxy nginx -s reload

# 5. Flip the funnel to TCP passthrough:
tailscale funnel --https=443 off
tailscale serve reset
bash tailscale/bootstrap-tcp.sh --apply

# 6. Verify from the public internet (use --resolve-less curl since you're
#    probably already on the tailnet and dig might lie to you):
curl -sS -o /dev/null -w "%{http_code}  %{ssl_verify_result}\n" \
  https://portal.deepaksharma.live/
# expect: 200  0   (200 status, 0 = TLS verified successfully)

# 7. Probe a handful of per-tool subdomains:
for host in portal api grafana ollama jenkins gitlab; do
  code=$(curl -sS -o /dev/null -w "%{http_code}" https://${host}.deepaksharma.live/)
  echo "${host}.deepaksharma.live  ${code}"
done
# expect: portal 200, api 200, grafana 200, ollama 401 (no creds), jenkins 403, gitlab 302

# 8. Schedule renewal (pick the appropriate provider flag):
#    Windows:
schtasks /Create /SC DAILY /ST 03:15 /TN "certbot-renew-deepaksharma" /TR ^
  "bash.exe -lc 'cd /c/Users/deepak/ai-folder && ./certbot/renew-cert.sh'"
#    WSL cron:
# 15 3 * * * cd /c/Users/deepak/ai-folder && ./certbot/renew-cert.sh >> certbot/logs/cron.log 2>&1

# 9. Commit the updated status doc so the repo reflects reality:
#    docs/PUBLIC_REACHABILITY_STATUS.md table row for DNS should go from NOT set -> OK,
#    LE cert row from NOT issued -> OK.
#    Do not commit secrets/godaddy.ini, secrets/cloudflare.ini, certbot/letsencrypt/,
#    or nginx-proxy/certs/*.pem — all are already gitignored.
```

If any step fails, section 9 restores the pre-branded baseline.
