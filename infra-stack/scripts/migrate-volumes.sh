#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

APPLY=false
FORCE=false
LIST_ONLY=false
MAP_FILE="${INFRA_VOLUME_MAP}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/migrate-volumes.sh --list
  ./scripts/migrate-volumes.sh --apply [--force]
  ./scripts/migrate-volumes.sh --apply --map /path/to/map.tsv

Map format (tab-separated):
  source_kind  source_name_or_path  target_kind  target_name_or_path  description

Kinds:
  volume   Docker named volume
  bind     Host bind path
  retain   Keep legacy data in place; do not copy
EOF
}

normalize_bind_path() {
  local path="$1"

  if [[ "${path}" =~ ^([A-Za-z]):/(.*)$ ]] && [[ -d /mnt ]]; then
    local drive="${BASH_REMATCH[1],,}"
    local rest="${BASH_REMATCH[2]}"
    printf '/mnt/%s/%s\n' "${drive}" "${rest}"
    return 0
  fi

  printf '%s\n' "${path}"
}

volume_exists() {
  docker volume inspect "$1" >/dev/null 2>&1
}

ensure_volume() {
  volume_exists "$1" || docker volume create "$1" >/dev/null
}

has_volume_data() {
  if ! volume_exists "$1"; then
    return 1
  fi

  docker run --rm -v "$1:/data" alpine:3.20 sh -c 'find /data -mindepth 1 -print -quit | grep -q .' >/dev/null 2>&1
}

has_bind_data() {
  local bind_path
  bind_path="$(normalize_bind_path "$1")"
  mkdir -p "${bind_path}"
  find "${bind_path}" -mindepth 1 -print -quit 2>/dev/null | grep -q .
}

copy_volume_to_volume() {
  local source_volume="$1"
  local target_volume="$2"
  ensure_volume "${target_volume}"
  docker run --rm \
    -v "${source_volume}:/from:ro" \
    -v "${target_volume}:/to" \
    alpine:3.20 sh -c 'cd /from && cp -a . /to'
}

copy_volume_to_bind() {
  local source_volume="$1"
  local target_path
  target_path="$(normalize_bind_path "$2")"
  mkdir -p "${target_path}"
  docker run --rm \
    -v "${source_volume}:/from:ro" \
    -v "${target_path}:/to" \
    alpine:3.20 sh -c 'cd /from && cp -a . /to'
}

while (($# > 0)); do
  case "$1" in
    --apply)
      APPLY=true
      ;;
    --force)
      FORCE=true
      ;;
    --list)
      LIST_ONLY=true
      ;;
    --map)
      shift
      MAP_FILE="${1:-}"
      [[ -n "${MAP_FILE}" ]] || infra_die "--map requires a file path"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      infra_die "Unknown argument: $1"
      ;;
  esac
  shift || true
done

[[ -f "${MAP_FILE}" ]] || infra_die "Volume map not found: ${MAP_FILE}"
infra_require_cmd docker

if ! ${APPLY} && ! ${LIST_ONLY}; then
  infra_note "Dry-run mode. Use --apply to copy data."
fi

while IFS=$'\t' read -r source_kind source_value target_kind target_value description; do
  [[ -n "${source_kind}" ]] || continue
  [[ "${source_kind}" =~ ^# ]] && continue

  printf '%s -> %s (%s)\n' "${source_kind}:${source_value}" "${target_kind}:${target_value}" "${description}"

  if ${LIST_ONLY}; then
    continue
  fi

  if [[ "${target_kind}" == "retain" ]]; then
    infra_note "Retaining ${source_value} in place."
    continue
  fi

  if [[ "${source_kind}" != "volume" ]]; then
    infra_warn "Unsupported source kind '${source_kind}' for ${source_value}; skipping."
    continue
  fi

  if ! volume_exists "${source_value}"; then
    infra_warn "Source volume missing: ${source_value}; skipping."
    continue
  fi

  case "${target_kind}" in
    volume)
      if ! ${FORCE} && has_volume_data "${target_value}"; then
        infra_warn "Destination volume '${target_value}' already has data; skipping."
        continue
      fi

      if ${APPLY}; then
        infra_note "Copying volume ${source_value} -> ${target_value}"
        copy_volume_to_volume "${source_value}" "${target_value}"
      fi
      ;;
    bind)
      if ! ${FORCE} && has_bind_data "${target_value}"; then
        infra_warn "Destination bind path '${target_value}' already has data; skipping."
        continue
      fi

      if ${APPLY}; then
        infra_note "Copying volume ${source_value} -> ${target_value}"
        copy_volume_to_bind "${source_value}" "${target_value}"
      fi
      ;;
    *)
      infra_warn "Unsupported target kind '${target_kind}' for ${target_value}; skipping."
      ;;
  esac
done < "${MAP_FILE}"
