#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
printf '[INFO] GitLab runner lifecycle is managed by infra-stack/scm.\n'
exec "${ROOT}/infra-stack/scripts/infra.sh" up gitlab-runner
