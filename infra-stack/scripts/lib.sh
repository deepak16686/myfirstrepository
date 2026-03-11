#!/usr/bin/env bash
set -euo pipefail

INFRA_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(cd "${INFRA_SCRIPT_DIR}/.." && pwd)"
INFRA_PROJECT="infra-stack"
INFRA_COMPOSE_FILE="${INFRA_ROOT}/docker-compose.yml"
INFRA_ENV_FILE="${INFRA_ROOT}/.env"
INFRA_VOLUME_MAP="${INFRA_ROOT}/volume-map.tsv"

INFRA_GROUP_NAMES=(
  security
  core
  ai
  scm
  cicd
  quality
  monitoring
  projects
)

declare -A INFRA_GROUPS=(
  [security]="nginx-proxy vault vault-init vault-unseal rbac-init"
  [core]="ai-postgres redis minio"
  [ai]="ollama chromadb chromadb-admin qdrant"
  [scm]="gitlab-server gitlab-runner gitea-server gitea-runner"
  [cicd]="jenkins-master jenkins-agent-1 jenkins-agent-2 jenkins-agent-3"
  [quality]="ai-sonarqube ai-sonar-db ai-nexus trivy-server"
  [monitoring]="prometheus grafana loki promtail jaeger node-exporter cadvisor ai-splunk"
  [projects]="jira jira-postgres redmine redmine-db"
)

declare -A INFRA_GROUP_DESCRIPTIONS=(
  [security]="reverse proxy, vault, bootstrap jobs"
  [core]="shared database, cache, object storage"
  [ai]="shared LLM and vector services"
  [scm]="GitLab, Gitea, runners"
  [cicd]="Jenkins master and inbound agents"
  [quality]="SonarQube, Nexus, Trivy"
  [monitoring]="metrics, logs, traces, dashboards"
  [projects]="Jira and Redmine"
)

infra_note() {
  printf '[INFO] %s\n' "$*"
}

infra_warn() {
  printf '[WARN] %s\n' "$*" >&2
}

infra_die() {
  printf '[ERROR] %s\n' "$*" >&2
  exit 1
}

infra_require_cmd() {
  command -v "$1" >/dev/null 2>&1 || infra_die "Missing required command: $1"
}

infra_compose() {
  local args=()
  if [[ -f "${INFRA_ENV_FILE}" ]]; then
    args+=(--env-file "${INFRA_ENV_FILE}")
  fi

  docker compose -p "${INFRA_PROJECT}" "${args[@]}" -f "${INFRA_COMPOSE_FILE}" "$@"
}

infra_expand_targets() {
  local target
  local expanded=()

  if (($# == 0)); then
    printf 'all\n'
    return 0
  fi

  for target in "$@"; do
    if [[ "${target}" == "all" ]]; then
      printf 'all\n'
      return 0
    fi

    if [[ -n "${INFRA_GROUPS[${target}]:-}" ]]; then
      local service
      for service in ${INFRA_GROUPS[${target}]}; do
        expanded+=("${service}")
      done
      continue
    fi

    expanded+=("${target}")
  done

  printf '%s\n' "${expanded[@]}" | awk '!seen[$0]++'
}

infra_print_groups() {
  local group
  for group in "${INFRA_GROUP_NAMES[@]}"; do
    printf '%-12s %s\n' "${group}" "${INFRA_GROUP_DESCRIPTIONS[${group}]}"
    printf '  %s\n' "${INFRA_GROUPS[${group}]}"
  done
}

infra_print_services() {
  local group
  for group in "${INFRA_GROUP_NAMES[@]}"; do
    for service in ${INFRA_GROUPS[${group}]}; do
      printf '%s\n' "${service}"
    done
  done | awk '!seen[$0]++'
}

infra_usage() {
  cat <<'EOF'
Usage:
  ./scripts/infra.sh up [all|group|service...]
  ./scripts/infra.sh stop [all|group|service...]
  ./scripts/infra.sh restart [all|group|service...]
  ./scripts/infra.sh down [all|group|service...]
  ./scripts/infra.sh logs [group|service...]
  ./scripts/infra.sh status
  ./scripts/infra.sh config
  ./scripts/infra.sh validate
  ./scripts/infra.sh seed nexus-images
  ./scripts/infra.sh seed nexus-language-stacks
  ./scripts/infra.sh migrate [--list|--apply|--force]
  ./scripts/infra.sh groups
  ./scripts/infra.sh services
EOF
}
