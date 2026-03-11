#!/usr/bin/env bash
# =============================================================================
# register-runner.sh
# Writes a GitLab runner config.toml and restarts the runner container.
# The runner is registered with the 'docker' tag and Docker-in-Docker support.
#
# Usage:
#   ./register-runner.sh [--token <RUNNER_TOKEN>] [--url <GITLAB_URL>]
# =============================================================================
set -euo pipefail

GITLAB_URL="${GITLAB_URL:-http://gitlab-server}"
RUNNER_TOKEN="${RUNNER_TOKEN:-glrtr-test-token-placeholder}"
RUNNER_CONTAINER="${RUNNER_CONTAINER:-gitlab-runner}"
CONFIG_PATH="gitlab-runner/config/config/config.toml"
CONCURRENT="${CONCURRENT:-3}"

# ── Parse arguments ───────────────────────────────────────────────────────────
while (($# > 0)); do
  case "$1" in
    --token|-t)   RUNNER_TOKEN="${2:-}"; shift ;;
    --url|-u)     GITLAB_URL="${2:-}"; shift ;;
    --container)  RUNNER_CONTAINER="${2:-}"; shift ;;
    -h|--help)
      cat <<'EOF'
Usage:
  ./register-runner.sh [options]

Options:
  --token, -t     GitLab runner registration token
  --url,   -u     GitLab URL (default: http://gitlab-server)
  --container     Runner container name (default: gitlab-runner)
  -h, --help      Show this message

Environment variables:
  GITLAB_URL      GitLab base URL
  RUNNER_TOKEN    Runner registration token
  RUNNER_CONTAINER Container name for the runner
EOF
      exit 0 ;;
    *) printf '[ERROR] Unknown argument: %s\n' "$1" >&2; exit 1 ;;
  esac
  shift
done

log_info() { printf '[INFO ] %s\n' "$*"; }
log_warn() { printf '[WARN ] %s\n' "$*" >&2; }
log_err()  { printf '[ERROR] %s\n' "$*" >&2; exit 1; }

# ── Write config.toml ─────────────────────────────────────────────────────────
log_info "Generating runner config.toml ..."
log_info "  GitLab URL    : ${GITLAB_URL}"
log_info "  Runner token  : ${RUNNER_TOKEN}"
log_info "  Container     : ${RUNNER_CONTAINER}"

mkdir -p "$(dirname "${CONFIG_PATH}")"

cat > "${CONFIG_PATH}" <<EOF
concurrent = ${CONCURRENT}
check_interval = 0
shutdown_timeout = 0

[session_server]
  session_timeout = 1800

[[runners]]
  name = "docker-dind-runner"
  url = "${GITLAB_URL}"
  token = "${RUNNER_TOKEN}"
  executor = "docker"
  clone_url = "${GITLAB_URL}"
  shell = "sh"
  tags = ["docker"]

  [runners.custom_build_dir]
    enabled = false

  [runners.cache]
    [runners.cache.s3]
    [runners.cache.gcs]
    [runners.cache.azure]

  [runners.docker]
    tls_verify = false
    image = "docker:24-cli"
    privileged = true
    disable_entrypoint_overwrite = false
    oom_kill_disable = false
    disable_cache = false
    volumes = ["/cache", "/var/run/docker.sock:/var/run/docker.sock"]
    shm_size = 2147483648
    network_mode = "global-infra-net"

    [[runners.docker.services]]
      name = "docker:24-dind"
      alias = "docker"
      command = ["--tls=false"]

    [[runners.docker.services]]
      name = "postgres:15-alpine"
      alias = "postgres"

    [[runners.docker.services]]
      name = "redis:7-alpine"
      alias = "redis"

    [[runners.docker.services]]
      name = "minio/minio:latest"
      alias = "minio"
EOF

log_info "config.toml written to ${CONFIG_PATH}"

# ── Copy config into running container ────────────────────────────────────────
if docker ps --format "{{.Names}}" | grep -q "^${RUNNER_CONTAINER}$"; then
  log_info "Copying config.toml into container '${RUNNER_CONTAINER}' ..."
  docker cp "${CONFIG_PATH}" "${RUNNER_CONTAINER}:/etc/gitlab-runner/config.toml"

  log_info "Restarting runner container ..."
  docker restart "${RUNNER_CONTAINER}"

  log_info "Runner restarted. Allow 10-30 seconds for it to appear as active in GitLab."
  printf '\nNext steps:\n'
  printf '  1. Open your project → Settings → CI/CD → Runners\n'
  printf '  2. Look for "docker-dind-runner" with tag "docker"\n'
  printf '  3. If still offline after 60s, update the token via the GitLab web UI\n'
else
  log_warn "Container '${RUNNER_CONTAINER}' is not running."
  log_warn "Config written locally; copy it manually when the container starts:"
  log_warn "  docker cp ${CONFIG_PATH} ${RUNNER_CONTAINER}:/etc/gitlab-runner/config.toml"
  log_warn "  docker restart ${RUNNER_CONTAINER}"
fi
