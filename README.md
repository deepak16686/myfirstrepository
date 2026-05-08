# AI Folder Workspace

This repository is organized around two top-level areas:

- `services/` - application and runtime service code.
- `infrastructure/` - compose files, reverse proxy, Cloudflare/Tailscale, certificates, runners, monitoring, Nexus, Kubernetes, and operational scripts.

## Main Portal Stack

The tested DevOps portal backend and UI code lives in `services/devops-tools-backend`.
The compose entrypoint that runs it with the public reverse proxy lives in
`infrastructure/compose/devops-tools/docker-compose.yml`.

Run from the repository root:

```powershell
docker compose --env-file services\devops-tools-backend\.env -f infrastructure\compose\devops-tools\docker-compose.yml up -d --build
```

Health check:

```powershell
docker exec devops-tools-backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8003/health', timeout=10).read().decode())"
```

Public portal:

```text
https://deepaksharma.live/chat
```

## Directory Map

| Path | Purpose |
| --- | --- |
| `services/devops-tools-backend` | FastAPI backend, bundled React/Vite portal UI, pipeline chatbot, GitLab/Jenkins/GitHub generators |
| `services/rag-ai` | RAG template corpus and helper scripts |
| `services/legacy-modernization-api` | Legacy modernization FastAPI sample service |
| `services/plane` | Project-management helper scripts |
| `infrastructure/compose` | Docker Compose entrypoints |
| `infrastructure/reverse-proxy/nginx` | Public nginx host/path router for `deepaksharma.live` |
| `infrastructure/cloudflare` | Cloudflare Tunnel setup |
| `infrastructure/tailscale` | Tailscale Funnel fallback setup |
| `infrastructure/certbot` | TLS certificate issuance and renewal |
| `infrastructure/gitlab-runner` | GitLab Runner config and test fixtures |
| `infrastructure/platform-setup` | Organized platform compose stack |
| `infrastructure/scripts` | Operational and e2e scripts |
| `docs` | Runbooks, URL maps, and validation evidence |
