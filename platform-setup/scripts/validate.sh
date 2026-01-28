#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

set -a
# shellcheck disable=SC1091
source ./.env
set +a

check() {
  local name="$1"
  local url="$2"
  if curl -fsS --max-time 5 "$url" >/dev/null; then
    printf "OK   %-18s %s\n" "$name" "$url"
  else
    printf "FAIL %-18s %s\n" "$name" "$url"
  fi
}

check "OpenWebUI" "http://localhost:${OPENWEBUI_PORT}/"
check "MinIO" "http://localhost:${MINIO_PORT}/minio/health/live"
check "ChromaDB" "http://localhost:${CHROMA_PORT}/api/v1/heartbeat"
check "Ollama" "http://localhost:${OLLAMA_PORT}/"
check "ModernizationAPI" "http://localhost:${MODERNIZATION_API_PORT}/api/v1/health"
check "Nexus" "http://localhost:${NEXUS_UI_PORT}/"
check "SonarQube" "http://localhost:${SONARQUBE_PORT}/api/system/health"
check "Redmine" "http://localhost:${REDMINE_PORT}/"
check "GitLab" "http://localhost:${GITLAB_HTTP_PORT}/-/health"
check "Prometheus" "http://localhost:${PROMETHEUS_PORT}/-/healthy"
check "Grafana" "http://localhost:${GRAFANA_PORT}/api/health"
check "Loki" "http://localhost:${LOKI_PORT}/ready"
check "Jaeger" "http://localhost:${JAEGER_UI_PORT}/"
check "Trivy" "http://localhost:${TRIVY_PORT}/healthz"

