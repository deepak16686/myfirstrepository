#!/usr/bin/env bash
# =============================================================================
# push-images-to-nexus.sh
# Pushes images into the Nexus Docker hosted registry (localhost:5001/apm-repo).
# Prefers images already running; supplements with a curated list to reach 20.
#
# Usage:
#   ./push-images-to-nexus.sh -u admin -p <password>
#   ./push-images-to-nexus.sh -u admin -p <password> --registry localhost:5001
#   ./push-images-to-nexus.sh -u admin -p <password> --repo apm-repo --ns demo
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

# ── Defaults ──────────────────────────────────────────────────────────────────
NEXUS_USER=""
NEXUS_PASS=""
REGISTRY_HOST="localhost"
REGISTRY_PORT="5001"
HOSTED_REPO="apm-repo"
NAMESPACE="demo"

# ── Parse arguments ───────────────────────────────────────────────────────────
usage() {
  cat <<'EOF'
Usage:
  ./scripts/push-images-to-nexus.sh -u <user> -p <password> [options]

Options:
  -u, --user      Nexus username          (required)
  -p, --password  Nexus password          (required)
  --registry      host:port               (default: localhost:5001)
  --repo          Hosted repo name        (default: apm-repo)
  --ns            Namespace inside repo   (default: demo)
  -h, --help      Show this message
EOF
}

while (($# > 0)); do
  case "$1" in
    -u|--user)      NEXUS_USER="${2:-}"; shift ;;
    -p|--password)  NEXUS_PASS="${2:-}"; shift ;;
    --registry)
      REGISTRY_HOST="${2%%:*}"
      REGISTRY_PORT="${2##*:}"
      shift ;;
    --repo)         HOSTED_REPO="${2:-}"; shift ;;
    --ns)           NAMESPACE="${2:-}"; shift ;;
    -h|--help)      usage; exit 0 ;;
    *) infra_die "Unknown argument: $1" ;;
  esac
  shift
done

[[ -n "${NEXUS_USER}" ]] || { usage; infra_die "-u/--user is required"; }
[[ -n "${NEXUS_PASS}" ]] || { usage; infra_die "-p/--password is required"; }

REGISTRY="${REGISTRY_HOST}:${REGISTRY_PORT}"

# ── Helpers ───────────────────────────────────────────────────────────────────
check_docker() {
  infra_note "Checking Docker daemon..."
  docker version >/dev/null
  infra_note "Docker reachable."
}

check_registry() {
  infra_note "Checking registry at http://${REGISTRY}/v2/ ..."
  local code
  code="$(curl -sSo /dev/null -w '%{http_code}' --max-time 10 \
    "http://${REGISTRY}/v2/" 2>/dev/null || true)"
  if [[ "${code}" == "200" || "${code}" == "401" ]]; then
    infra_note "Registry reachable (HTTP ${code})."
  else
    infra_warn "Registry check returned HTTP ${code:-curl-error}. Continuing anyway."
  fi
}

docker_login() {
  infra_note "Logging in to ${REGISTRY} as ${NEXUS_USER} ..."
  printf '%s' "${NEXUS_PASS}" | docker login "${REGISTRY}" \
    -u "${NEXUS_USER}" --password-stdin
  infra_note "Login succeeded."
}

ensure_pulled() {
  local image="$1"
  if docker image inspect "${image}" >/dev/null 2>&1; then
    infra_note "Already present locally: ${image}"
  else
    infra_note "Pulling: ${image}"
    docker pull "${image}"
  fi
}

tag_and_push() {
  local src="$1"
  local dest="$2"
  infra_note "Tag:  ${src}  ->  ${dest}"
  docker tag "${src}" "${dest}"
  infra_note "Push: ${dest}"
  docker push "${dest}"
}

sanitize_name() {
  local name="${1,,}"                      # lowercase
  name="${name//:/-}"                      # colon → dash
  name="${name//\//-}"                     # slash → dash
  name="${name//\./-}"                     # dot   → dash
  name="${name//[^a-z0-9\-]/}"            # strip anything else
  name="${name##-}"; name="${name%%-}"     # trim leading/trailing dashes
  printf '%s' "${name}"
}

# ── Build candidate list ───────────────────────────────────────────────────────
mapfile -t RUNNING < <(docker ps --format "{{.Image}}" | sort -u)

EXTRAS=(
  "alpine:3.20"
  "busybox:1.36"
  "hello-world:latest"
  "nginx:1.27-alpine"
  "httpd:2.4-alpine"
  "traefik:v3.1"
  "registry:2"
  "rabbitmq:3-alpine"
  "memcached:1.6-alpine"
  "hashicorp/vault:1.17"
  "grafana/grafana:11.1.0"
  "prom/prometheus:v2.55.0"
  "node:20-alpine"
  "python:3.12-alpine"
  "openjdk:21-jdk-slim"
  "debian:bookworm-slim"
  "ubuntu:24.04"
  "curlimages/curl:8.10.1"
  "busybox:stable"
  "alpine:latest"
)

# Merge: running first, then extras — deduplicated
declare -A SEEN=()
CANDIDATES=()
for img in "${RUNNING[@]}" "${EXTRAS[@]}"; do
  [[ -v SEEN["${img}"] ]] && continue
  SEEN["${img}"]=1
  CANDIDATES+=("${img}")
  (( ${#CANDIDATES[@]} >= 20 )) && break
done

(( ${#CANDIDATES[@]} >= 20 )) || \
  infra_die "Not enough candidates to reach 20 (got ${#CANDIDATES[@]})."

# ── Main ──────────────────────────────────────────────────────────────────────
check_docker
check_registry
docker_login

infra_note "Pushing 20 images into ${REGISTRY}/${HOSTED_REPO}/${NAMESPACE} ..."
printf '\n'

index=1
for src in "${CANDIDATES[@]:0:20}"; do
  ensure_pulled "${src}"

  safe="$(sanitize_name "${src}")"
  tag="$(printf 'demo-%02d' "${index}")"
  dest="${REGISTRY}/${HOSTED_REPO}/${NAMESPACE}/${safe}:${tag}"

  tag_and_push "${src}" "${dest}"
  (( index++ ))
done

printf '\n'
infra_note "Done. 20 images pushed to ${REGISTRY}/${HOSTED_REPO}/${NAMESPACE}"
infra_note "Browse in Nexus UI → Browse → ${HOSTED_REPO}"
infra_note "Example pull:"
printf '  docker pull %s/%s/%s/alpine-3-20:demo-01\n' \
  "${REGISTRY}" "${HOSTED_REPO}" "${NAMESPACE}"
