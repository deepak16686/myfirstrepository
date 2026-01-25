#!/usr/bin/env bash
set -euo pipefail

# -----------------------------
# Nexus Docker registry settings
# -----------------------------
NEXUS_DOCKER_HOST="${NEXUS_DOCKER_HOST:-localhost}"
NEXUS_DOCKER_PORT="${NEXUS_DOCKER_PORT:-8082}"     # Docker connector port (NOT UI port 8081)
NEXUS_REPO="${NEXUS_REPO:-apm-repo}"               # repo name as seen in Nexus Browse
NAMESPACE="${NAMESPACE:-demo}"                     # folder under repo (you want demo)

NEXUS_USERNAME="${NEXUS_USERNAME:-admin}"
NEXUS_PASSWORD="${NEXUS_PASSWORD:-}"               # provide via env var or prompt

# Optional: provide a list file with image:tag per line
IMAGES_FILE="${IMAGES_FILE:-}"

DEFAULT_IMAGES=(
  "python:3.12-slim"
  "python:3.11-slim"
  "eclipse-temurin:21-jre"
  "eclipse-temurin:17-jre"
  "node:22-alpine"
  "node:20-alpine"
  "nginx:1.27-alpine"
  "alpine:3.20"
  "ubuntu:24.04"
  "redis:7-alpine"
  "postgres:16-alpine"
)

# -----------------------------
# Helpers
# -----------------------------
die(){ echo "ERROR: $*" >&2; exit 1; }
require(){ command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

REGISTRY="${NEXUS_DOCKER_HOST}:${NEXUS_DOCKER_PORT}"

login() {
  if [[ -z "${NEXUS_PASSWORD}" ]]; then
    echo -n "Enter Nexus password for user '${NEXUS_USERNAME}': "
    read -rs NEXUS_PASSWORD
    echo
  fi
  echo "${NEXUS_PASSWORD}" | docker login "${REGISTRY}" -u "${NEXUS_USERNAME}" --password-stdin
}

load_images() {
  if [[ -n "${IMAGES_FILE}" ]]; then
    [[ -f "${IMAGES_FILE}" ]] || die "IMAGES_FILE not found: ${IMAGES_FILE}"
    # ignore comments and blank lines
    grep -vE '^\s*#|^\s*$' "${IMAGES_FILE}"
  else
    printf '%s\n' "${DEFAULT_IMAGES[@]}"
  fi
}

target_ref() {
  # repo-path mode target:
  # <host:port>/<repo>/<namespace>/<image>:<tag>
  local src="$1"
  echo "${REGISTRY}/${NEXUS_REPO}/${NAMESPACE}/${src}"
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

  echo "Done : ${dst}"
}

verify_image() {
  # Verify via Docker V2 tags API inside repo-path mode:
  # /v2/<repo>/<namespace>/<name>/tags/list
  local name="$1"
  local url="http://${NEXUS_DOCKER_HOST}:${NEXUS_DOCKER_PORT}/v2/${NEXUS_REPO}/${NAMESPACE}/${name}/tags/list"
  echo "Verify (tags/list): ${url}"
  curl -s -u "${NEXUS_USERNAME}:${NEXUS_PASSWORD}" "${url}" || true
  echo
}

# -----------------------------
# Main
# -----------------------------
require docker
require curl

login

# Push all images
while IFS= read -r img; do
  push_one "${img}"
done < <(load_images)

echo "============================================================"
echo "All images pushed into: ${REGISTRY}/${NEXUS_REPO}/${NAMESPACE}/"
echo "Nexus UI path: Browse -> ${NEXUS_REPO} -> v2/${NEXUS_REPO}/${NAMESPACE}/"
echo "============================================================"

# Example verification for python (optional)
verify_image "python"
