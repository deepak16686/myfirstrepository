#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for arg in "$@"; do
  case "${arg}" in
    --validate|-Validate)
      exec "${ROOT}/infra-stack/scripts/validate.sh"
      ;;
    --skip-models|-SkipModels|--skip-monitoring|-SkipMonitoring)
      printf '[WARN] Ignoring legacy flag: %s\n' "${arg}" >&2
      ;;
    *)
      printf '[WARN] Ignoring unsupported legacy argument: %s\n' "${arg}" >&2
      ;;
  esac
done

exec "${ROOT}/infra-stack/scripts/infra.sh" up all
