# Infrastructure Stack

`infra-stack` is the canonical shared infrastructure for everything under `ai-folder`.

Use this stack as the long-lived control plane for shared services. Do not spin up duplicate copies from `platform-setup`, `files`, or ad hoc PowerShell scripts.

## Service Groups

- `security`: `nginx-proxy`, `vault`, `vault-init`, `vault-unseal`, `rbac-init`
- `core`: `ai-postgres`, `redis`, `minio`
- `ai`: `ollama`, `chromadb`, `chromadb-admin`, `qdrant`
- `scm`: `gitlab-server`, `gitlab-runner`, `gitea-server`, `gitea-runner`
- `cicd`: `jenkins-master`, `jenkins-agent-1`, `jenkins-agent-2`, `jenkins-agent-3`
- `quality`: `ai-sonarqube`, `ai-sonar-db`, `ai-nexus`, `trivy-server`
- `monitoring`: `prometheus`, `grafana`, `loki`, `promtail`, `jaeger`, `node-exporter`, `cadvisor`, `ai-splunk`
- `projects`: `jira`, `jira-postgres`, `redmine`, `redmine-db`

## Canonical Shell Workflow

```bash
cd infra-stack
./scripts/infra.sh up all
./scripts/infra.sh status
./scripts/infra.sh logs grafana
./scripts/validate.sh
```

Target a single group or service:

```bash
./scripts/infra.sh up scm
./scripts/infra.sh restart ai-nexus
./scripts/infra.sh stop monitoring
```

The operational scripts never remove volumes. `down` is intentionally treated as a non-destructive stop alias.

## Data Safety

- Canonical data is mounted from existing external Docker volumes or existing host bind paths.
- Legacy `platform-*` volumes are not deleted or overwritten automatically.
- Use `./scripts/migrate-volumes.sh --list` to review the migration map.
- Use `./scripts/migrate-volumes.sh --apply` only when you are ready to copy data into the canonical infra targets.

The migration script is dry-run by default and refuses to overwrite populated destinations unless `--force` is passed.

## Volume Notes

- GitLab stays on the existing bind mounts under `C:/Users/deepak/gitlab_docker`.
- Core and monitoring services keep using the long-lived shared volumes already referenced by `infra-stack`.
- `platform-open-webui-data` is intentionally retained as legacy app data because `open-webui` is not part of the shared infra control plane.

## Legacy Folders

These folders now exist only as compatibility entrypoints or archived references:

- `platform-setup`
- `files`
- `desktop-content/files`

Use the shell wrappers there only if you need a transitional command path. They now route back to `infra-stack`.
