# Infrastructure

Infrastructure and operations code lives here. Service source code belongs under
`../services`.

| Path | Purpose |
| --- | --- |
| `compose/devops-tools/docker-compose.yml` | Main DevOps portal and nginx proxy compose entrypoint |
| `compose/*.yml` | Standalone supporting compose stacks |
| `reverse-proxy/nginx` | `deepaksharma.live` nginx routing, cert mounts, and htpasswd template |
| `cloudflare` | Cloudflare Tunnel setup |
| `tailscale` | Tailscale Funnel fallback setup |
| `certbot` | Wildcard certificate issuance and renewal scripts |
| `gitlab-runner` | Runner config, compose, registration, and test pipeline fixture |
| `kubernetes/prod` | Kubernetes production manifests |
| `monitoring` | Prometheus configuration |
| `nexus` | Nexus image seeding scripts |
| `platform-setup` | Standalone platform compose stack |
| `scripts` | Auth, e2e, GitLab, and ops scripts |
| `sonarqube` | SonarQube project import/export files |
