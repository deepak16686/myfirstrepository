# Platform Setup (Organized)

This folder is a clean, self-contained setup that does **not** modify the existing files or running stack. It provides:
- A single `docker-compose.yml`
- A single shared network (`platform-net`) so every container can reach every other container
- Shell-only scripts in `scripts/`
- Centralized configuration under `config/`

If your current stack is running, change ports in `.env` before starting this one.

## Quick start

```bash
cd platform-setup
./scripts/up.sh
```

## Stop

```bash
./scripts/down.sh
```

## Logs

```bash
./scripts/logs.sh
```

## Status

```bash
./scripts/status.sh
```

## Health check

```bash
./scripts/validate.sh
```

## Services and default ports

- PostgreSQL: 5432
- Redis: 6379
- MinIO: 9000 / 9001
- ChromaDB: 8000
- Ollama: 11434
- Open WebUI: 3001
- Modernization API: 8002
- Nexus: 8081 (UI), 5001 (Docker)
- SonarQube: 9002
- Redmine: 8090
- GitLab: 8929 (HTTP), 2222 (SSH)
- Prometheus: 9090
- Grafana: 3000
- Loki: 3100
- Jaeger UI: 16686
- Trivy: 8083

## Notes

- All containers are attached to a single bridge network (`platform-net`).
- Named volumes are used for persistence, prefixed with `platform-` to avoid clashing with existing volumes.
- GitLab initial root password is set via `GITLAB_ROOT_PASSWORD` in `.env`.
- Nexus admin password is stored in the volume (`platform-nexus-data/admin.password`) on first start.

## Nexus image seeding (optional)

```bash
./scripts/seed-nexus-images.sh
./scripts/seed-nexus-language-stacks.sh
```

