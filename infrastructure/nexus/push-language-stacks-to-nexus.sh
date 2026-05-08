#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Nexus Docker (hosted) repo config (based on your screenshot)
# ============================================================
REGISTRY_HOST="${REGISTRY_HOST:-localhost}"
REGISTRY_PORT="${REGISTRY_PORT:-5001}"     # <-- correct Docker connector port
REPO="${REPO:-apm-repo}"                   # Nexus repo name (docker hosted)
NAMESPACE="${NAMESPACE:-demo}"             # folder under repo

NEXUS_USERNAME="${NEXUS_USERNAME:-admin}"
NEXUS_PASSWORD="${NEXUS_PASSWORD:-}"       # set via env var or prompt

REGISTRY="${REGISTRY_HOST}:${REGISTRY_PORT}"

# ============================================================
# Image sets (>= 5 versions per language)
# Notes:
# - "React" is typically built using Node, then served with nginx/caddy.
# - For Java we use Eclipse Temurin JRE/JDK variants.
# ============================================================

PYTHON_IMAGES=(
  "python:3.13-slim"
  "python:3.12-slim"
  "python:3.11-slim"
  "python:3.10-slim"
  "python:3.9-slim"
)

JAVA_IMAGES=(
  "eclipse-temurin:21-jdk"
  "eclipse-temurin:21-jre"
  "eclipse-temurin:17-jdk"
  "eclipse-temurin:17-jre"
  "eclipse-temurin:11-jre"
)

NODE_IMAGES=(
  "node:22-alpine"
  "node:22-slim"
  "node:20-alpine"
  "node:20-slim"
  "node:18-alpine"
)

# "Other images as well" – useful base + infra + web-serving for React artifacts
OTHER_IMAGES=(
  "nginx:1.27-alpine"
  "caddy:2.9-alpine"
  "alpine:3.20"
  "ubuntu:24.04"
  "debian:bookworm-slim"
  "busybox:1.36"
  "redis:7-alpine"
  "postgres:16-alpine"
  "mongo:7"
  "rabbitmq:3-alpine"
  "haproxy:3.1-alpine"
  "traefik:v3.1"
)

# ============================================================
# Helpers
# ============================================================
die() { echo "ERROR: $*" >&2; exit 1; }
require() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

login_registry() {
  if [[ -z "${NEXUS_PASSWORD}" ]]; then
    echo -n "Enter Nexus password for user '${NEXUS_USERNAME}': "
    read -rs NEXUS_PASSWORD
    echo
  fi
  echo "${NEXUS_PASSWORD}" | docker login "${REGISTRY}" -u "${NEXUS_USERNAME}" --password-stdin
}

target_ref() {
  # Path-based routing into Nexus docker hosted repo:
  # <host:port>/<repo>/<namespace>/<image>:<tag>
  local src="$1"
  echo "${REGISTRY}/${REPO}/${NAMESPACE}/${src}"
}

push_one() {
  local src="$1"
  local dst
  dst="$(target_ref "${src}")"

  echo "------------------------------------------------------------"
  echo "Pull : ${src}"
  docker pull "${src}"

  echo "Tag  : ${src} -> ${dst}"
  docker tag "${src}" "${dst}"

  echo "Push : ${dst}"
  docker push "${dst}"

  # Best-effort verification (non-fatal if your Docker doesn't support it)
  if docker manifest inspect "${dst}" >/dev/null 2>&1; then
    echo "Verify: OK (manifest present)"
  else
    echo "Verify: skipped (manifest inspect not available / not permitted)"
  fi

  echo "Done : ${dst}"
}

push_group() {
  local title="$1"; shift
  local -a imgs=("$@")

  echo
  echo "===================="
  echo "Pushing: ${title}"
  echo "Count : ${#imgs[@]}"
  echo "===================="

  for img in "${imgs[@]}"; do
    push_one "${img}"
  done
}

# ============================================================
# Main
# ============================================================
require docker
login_registry

push_group "Python (>=5 versions)" "${PYTHON_IMAGES[@]}"
push_group "Java / Temurin (>=5 variants)" "${JAVA_IMAGES[@]}"
push_group "Node.js (>=5 versions/variants)" "${NODE_IMAGES[@]}"
push_group "Other foundational images" "${OTHER_IMAGES[@]}"

echo
echo "============================================================"
echo "Completed push to Nexus:"
echo "  ${REGISTRY}/${REPO}/${NAMESPACE}/"
echo "Browse in UI:"
echo "  Browse -> ${REPO} -> v2/${REPO}/${NAMESPACE}/"
echo "============================================================"
