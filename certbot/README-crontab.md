# Auto-renewal: crontab + Windows Task Scheduler

`certbot/renew-cert.sh` is idempotent. Certbot itself only renews a lineage
when it has <30 days remaining (verified at
<https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates>),
and this script exits 0 early with a `not due` message if the expiry is still
more than 30 days out. That means you can run it **daily** without any
downside; the only actions that happen are the API call to Let's Encrypt
(which is free), the nginx reload (cheap), and the log write.

Two fire paths for a Windows 11 + WSL2 + Docker Desktop box:

---

## Path A — Windows Task Scheduler (preferred for Windows hosts)

Runs even when WSL is not open. Docker Desktop must be running for the
`docker compose run` inside the script to succeed; if Docker Desktop is off
when the task fires, the script exits non-zero and the Task-Scheduler
retry-count picks it up on the next run.

### A1. Create `renew-cert.bat` (host-side wrapper)

Save as `C:\Users\deepak\ai-folder\certbot\renew-cert.bat`:

```bat
@echo off
REM --- Windows Task Scheduler wrapper around the bash script ---
REM Launch Git Bash, execute the script, propagate the exit code.
"C:\Program Files\Git\bin\bash.exe" -lc "cd /c/Users/deepak/ai-folder && ./certbot/renew-cert.sh --provider=cloudflare >> certbot/logs/task-scheduler.log 2>&1"
exit /b %ERRORLEVEL%
```

### A2. Register the task (admin PowerShell)

```powershell
$Action  = New-ScheduledTaskAction -Execute 'C:\Users\deepak\ai-folder\certbot\renew-cert.bat'
$Trigger = New-ScheduledTaskTrigger -Daily -At 3:17am
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartInterval (New-TimeSpan -Hours 6) `
    -RestartCount 3 `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName "LetsEncrypt-Renew-DeepakSharmaLive" `
    -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings `
    -Description "Daily certbot renewal for *.deepaksharma.live"
```

Why `3:17am`? Off-peak, avoids the top-of-hour thundering herd against
Let's Encrypt. Any random minute between 00 and 59 is fine.

### A3. Verify

```powershell
Get-ScheduledTaskInfo -TaskName "LetsEncrypt-Renew-DeepakSharmaLive"
# Expected after the first run:
#   LastRunTime    : 2026-04-20 03:17:04
#   LastTaskResult : 0
#   NumberOfMissedRuns : 0
```

Tail the log for the last run:

```bash
tail -n 40 /c/Users/deepak/ai-folder/certbot/logs/task-scheduler.log
```

Expected on a not-due day:

```
================================================================
 renew-cert.sh start  2026-04-20T03:17:04-07:00
   provider: cloudflare   force: 0   domain: deepaksharma.live
================================================================
[INFO] lineage deepaksharma.live has 78 days remaining
[OK]  not due (>30 days remain); exit 0
```

Expected on a renewal day:

```
[INFO] lineage deepaksharma.live has 27 days remaining
[INFO] running: docker compose -f certbot/docker-compose.certbot.yml run --rm certbot-renew
Saving debug log to /var/log/letsencrypt/letsencrypt.log
Processing /etc/letsencrypt/renewal/deepaksharma.live.conf
...
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/deepaksharma.live/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/deepaksharma.live/privkey.pem
This certificate expires on 2026-07-18.
[OK]  mirrored to /c/Users/deepak/ai-folder/nginx-proxy/certs
[OK]  reloaded nginx-proxy
```

---

## Path B — WSL cron (only if you keep WSL running 24/7)

WSL2 cron only runs while the WSL instance is up; if you close all WSL
terminals it suspends. For a developer desktop this is usually NOT what you
want — use Path A. If you're keeping WSL alive via
`wsl --install` autostart or `systemd-cron`, this works:

### B1. Install cron inside WSL

```bash
# Ubuntu WSL
sudo apt-get update && sudo apt-get install -y cron
sudo service cron start
sudo systemctl enable cron   # if systemd is enabled in /etc/wsl.conf
```

### B2. Add the crontab entry

```bash
( crontab -l 2>/dev/null; cat <<'EOF'
# Let's Encrypt wildcard cert renewal — *.deepaksharma.live
# Daily at 03:17 local. Script exits 0 early if >30 days remain.
17 3 * * * cd /mnt/c/Users/deepak/ai-folder && ./certbot/renew-cert.sh --provider=cloudflare >> certbot/logs/cron.log 2>&1
EOF
) | crontab -
```

Verify:

```bash
crontab -l | grep renew-cert
grep 'renew-cert' /var/log/syslog | tail -5   # or journalctl -u cron
```

### B3. WSL-cron caveat

`cd /mnt/c/...` crosses the WSL filesystem boundary — I/O is 10-100x slower
than `$HOME`. For this script the penalty is negligible (few KB of cert data)
but note the general principle: heavy-IO repos should live under `$HOME` in
WSL, not `/mnt/c`.

---

## Health-check the renewal pipeline (recommended, both paths)

Add a one-shot sanity check that verifies the nginx-proxy is serving the
correct cert:

```bash
# curl --insecure on purpose — we want to see the cert even if the client
# doesn't trust it (eg. staging).
echo | openssl s_client -connect deepaksharma.live:443 -servername deepaksharma.live 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates
```

Expected in prod:

```
subject=CN = deepaksharma.live
issuer=C = US, O = Let's Encrypt, CN = R3
notBefore=Apr 19 00:00:00 2026 GMT
notAfter=Jul 18 23:59:59 2026 GMT
```

If `issuer` contains `(STAGING)` you're still on the staging path — re-issue
without `--dry-run`.
