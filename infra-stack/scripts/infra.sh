#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

command_name="${1:-}"
if [[ -z "${command_name}" ]]; then
  infra_usage
  exit 1
fi
shift || true

case "${command_name}" in
  up)
    infra_require_cmd docker
    mapfile -t targets < <(infra_expand_targets "$@")
    if [[ "${targets[0]}" == "all" ]]; then
      infra_note "Starting the full shared infrastructure stack."
      infra_compose up -d
    else
      infra_note "Starting: ${targets[*]}"
      infra_compose up -d "${targets[@]}"
    fi
    ;;
  stop)
    infra_require_cmd docker
    mapfile -t targets < <(infra_expand_targets "$@")
    if [[ "${targets[0]}" == "all" ]]; then
      infra_note "Stopping the full shared infrastructure stack without removing data."
      infra_compose stop
    else
      infra_note "Stopping: ${targets[*]}"
      infra_compose stop "${targets[@]}"
    fi
    ;;
  down)
    infra_require_cmd docker
    infra_warn "'down' is treated as a safe stop alias. No volumes will be removed."
    mapfile -t targets < <(infra_expand_targets "$@")
    if [[ "${targets[0]}" == "all" ]]; then
      infra_compose stop
    else
      infra_compose stop "${targets[@]}"
    fi
    ;;
  restart)
    infra_require_cmd docker
    mapfile -t targets < <(infra_expand_targets "$@")
    if [[ "${targets[0]}" == "all" ]]; then
      infra_note "Restarting the full shared infrastructure stack."
      infra_compose restart
    else
      infra_note "Restarting: ${targets[*]}"
      infra_compose restart "${targets[@]}"
    fi
    ;;
  logs)
    infra_require_cmd docker
    mapfile -t targets < <(infra_expand_targets "$@")
    if [[ "${targets[0]}" == "all" ]]; then
      exec infra_compose logs -f --tail=200
    fi
    exec infra_compose logs -f --tail=200 "${targets[@]}"
    ;;
  status|ps)
    infra_require_cmd docker
    exec infra_compose ps
    ;;
  config)
    infra_require_cmd docker
    exec infra_compose config
    ;;
  validate)
    exec "${SCRIPT_DIR}/validate.sh"
    ;;
  migrate)
    exec "${SCRIPT_DIR}/migrate-volumes.sh" "$@"
    ;;
  seed)
    infra_require_cmd docker
    subcommand="${1:-}"
    case "${subcommand}" in
      nexus-images)
        shift || true
        exec "${INFRA_ROOT}/../nexus/push-images-to-nexus.sh" "$@"
        ;;
      nexus-language-stacks)
        shift || true
        exec "${INFRA_ROOT}/../nexus/push-language-stacks-to-nexus.sh" "$@"
        ;;
      *)
        infra_die "Unknown seed target: ${subcommand:-<missing>}"
        ;;
    esac
    ;;
  groups)
    infra_print_groups
    ;;
  services)
    infra_print_services
    ;;
  *)
    infra_usage
    infra_die "Unknown command: ${command_name}"
    ;;
esac
