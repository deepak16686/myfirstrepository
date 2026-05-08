#!/usr/bin/env bash
set -euo pipefail

# ---------------------------
# Configuration (EDIT THESE)
# ---------------------------

# This must be the Docker registry endpoint (NOT the 8081 UI URL).
# Examples:
#   NEXUS_REGISTRY="localhost:8082"
#   NEXUS_REGISTRY="localhost:5000"
NEXUS_REGISTRY="${NEXUS_REGISTRY:-localhost:8082}"

# If your Nexus is configured with a "repository path" prefix for Docker hosted,
# set this to the repository name. Often, for Nexus Docker hosted, the repo name
# is not part of the image path, but sometimes it is.
# Try with empty first. If pushes fail with "repository does not allow...", set it.
NEXUS_REPO_PATH="${NEXUS_REPO_PATH:-}"

# Your Nexus username (safe to keep here)
NEXUS_USERNAME="${NEXUS_USERNAME:-admin}"

# DO NOT hardcode the password. Provide it via env var or prompt.
# export NEXUS_PASSWORD="..."
NEXUS_PASSWORD="${NEXUS_PASSWORD:-}"

# Optional: file listing images (one per line). If empty, uses default list.
IMAGES_FILE="${IMAGES_FILE:-}"

# Default curated list (extend as needed)
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

# ---------------------------
# Helpers
# ---------------------------

die() { echo "ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

nexus_login() {
  echo "Logging into Nexus registry: ${NEXUS_REGISTRY}"
  if [[ -z "${NEXUS_PASSWORD}" ]]; then
    echo -n "Enter Nexus password for ${NEXUS_USERNAME}: "
    read -rs NEXUS_PASSWORD
    echo
  fi
  echo "${NEXUS_PASSWORD}" | docker login "${NEXUS_REGISTRY}" -u "${NEXUS_USERNAME}" --password-stdin
}

target_ref() {
  # Convert "python:3.12-slim" to something like:
  #   localhost:8082/python:3.12-slim
  # or if NEXUS_REPO_PATH is set:
  #   localhost:8082/apm-repo/python:3.12-slim
  local src="$1"
  if [[ -n "${NEXUS_REPO_PATH}" ]]; then
    echo "${NEXUS_REGISTRY}/${NEXUS_REPO_PATH}/${src}"
  else
    echo "${NEXUS_REGISTRY}/${src}"
  fi
}

push_one() {
  local src="$1"
  local dst
  dst="$(target_ref "${src}")"

  echo "------------------------------------------------------------"
  echo "Pull  : ${src}"
  docker pull "${src}"

  echo "Tag   : ${src} -> ${dst}"
  docker tag "${src}" "${dst}"

  echo "Push  : ${dst}"
  docker push "${dst}"

  echo "Done  : ${dst}"
}

load_images() {
  if [[ -n "${IMAGES_FILE}" ]]; then
    [[ -f "${IMAGES_FILE}" ]] || die "IMAGES_FILE not found: ${IMAGES_FILE}"
    mapfile -t imgs < <(grep -vE '^\s*#|^\s*$' "${IMAGES_FILE}")
    printf '%s\n' "${imgs[@]}"
  else
    printf '%s\n' "${DEFAULT_IMAGES[@]}"
  fi
}

# ---------------------------
# Main
# ---------------------------

require_cmd docker

nexus_login

while IFS= read -r img; do
  push_one "${img}"
done < <(load_images)

echo "All images processed successfully."
