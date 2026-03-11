#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${ROOT}/infra-stack/scripts/infra.sh" up gitlab-server gitlab-runner gitea-server gitea-runner
