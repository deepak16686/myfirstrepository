#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

PASS_COUNT=0
FAIL_COUNT=0

print_result() {
  local status="$1"
  local name="$2"
  local detail="$3"

  if [[ "${status}" == "OK" ]]; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi

  printf '%-4s %-20s %s\n' "${status}" "${name}" "${detail}"
}

check_tcp() {
  local name="$1"
  local port="$2"

  if timeout 5 bash -lc ":</dev/tcp/127.0.0.1/${port}" >/dev/null 2>&1; then
    print_result "OK" "${name}" "tcp:${port}"
  else
    print_result "FAIL" "${name}" "tcp:${port}"
  fi
}

check_http() {
  local name="$1"
  local url="$2"
  shift 2
  local allowed_codes=("$@")
  local code
  code="$(curl -k -sS -o /dev/null -w '%{http_code}' --max-time 5 "${url}" 2>/dev/null || true)"

  local allowed
  for allowed in "${allowed_codes[@]}"; do
    if [[ "${code}" == "${allowed}" ]]; then
      print_result "OK" "${name}" "${url} -> ${code}"
      return 0
    fi
  done

  print_result "FAIL" "${name}" "${url} -> ${code:-curl-error}"
}

printf 'Infra validation for %s\n' "${INFRA_PROJECT}"
printf '%-4s %-20s %s\n' "----" "--------------------" "----------------------------------------"

check_http "nginx-proxy" "http://localhost:8443/" 200
check_http "vault" "http://localhost:8200/v1/sys/health" 200 429 472 473 501
check_tcp  "ai-postgres" 5432
check_tcp  "redis" 6379
check_http "minio" "http://localhost:9000/minio/health/live" 200
check_http "ollama" "http://localhost:11434/api/tags" 200
check_http "chromadb" "http://localhost:8005/api/v2/heartbeat" 200
check_http "chromadb-admin" "http://localhost:3001/" 200
check_http "qdrant" "http://localhost:6333/readyz" 200
check_http "gitlab" "http://localhost:8929/gitlab/users/sign_in" 200
check_http "gitea" "http://localhost:3002/api/healthz" 200
check_http "jenkins" "http://localhost:8080/jenkins/login" 200
check_http "sonarqube" "http://localhost:9002/api/system/status" 200
check_http "nexus" "http://localhost:8181/" 200
check_http "trivy" "http://localhost:8183/version" 200
check_http "prometheus" "http://localhost:9090/prometheus/-/healthy" 200
check_http "grafana" "http://localhost:3000/api/health" 200
check_http "loki" "http://localhost:3100/ready" 200
check_http "jaeger" "http://localhost:16686/" 200
check_http "node-exporter" "http://localhost:9100/metrics" 200
check_http "cadvisor" "http://localhost:8182/healthz" 200
check_tcp  "splunk-hec" 8088
check_tcp  "splunk-ui" 10000
check_http "jira" "http://localhost:8180/" 200 302
check_http "redmine" "http://localhost:8090/" 200 302

printf '\nPassed: %d  Failed: %d\n' "${PASS_COUNT}" "${FAIL_COUNT}"

if ((FAIL_COUNT > 0)); then
  exit 1
fi
