#!/usr/bin/env bash
# ============================================================================
# discover_local_repos.sh
# ----------------------------------------------------------------------------
# Walks the user's workspace looking for every git repository and emits a
# single JSON array on stdout describing each one. Safe to redirect to a file:
#
#     ./discover_local_repos.sh > inventory.json
#
# The script is read-only: it runs `git` with -C against each repo, never
# modifies anything, never fetches from any remote, never prints secrets.
#
# Usage:
#     ./discover_local_repos.sh [ROOT]
#
# ROOT defaults to /c/Users/deepak (the WSL/Git-Bash view of C:\Users\deepak).
# Override with a CLI arg or the WORKSPACE_ROOT env var.
#
# Skips well-known junk directories listed in PRUNE_NAMES so we don't descend
# into node_modules / .venv / dist / build / target / .next / .terraform /
# vendor / .gradle / __pycache__ / chromadb-data etc.
#
# Requires: bash 4+, find, git, awk, sed. jq is OPTIONAL (used only for
# post-processing/pretty-printing by the operator); the script emits valid
# JSON with no external help.
# ============================================================================

set -u
set -o pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT="${1:-${WORKSPACE_ROOT:-/c/Users/deepak}}"
MAX_DEPTH="${MAX_DEPTH:-8}"

# Directories we refuse to descend into (matched by basename via find -prune).
PRUNE_NAMES=(
  node_modules
  .venv
  venv
  env
  .env
  dist
  build
  out
  target
  .next
  .nuxt
  .terraform
  .gradle
  .idea
  .vscode
  __pycache__
  .pytest_cache
  .mypy_cache
  .ruff_cache
  .tox
  coverage
  .coverage
  htmlcov
  .cache
  vendor
  bower_components
  .DS_Store
  chromadb-data
  ollama-data
  minio-data
  postgres-data
  redis-data
  pg-data
  qdrant-data
  .parcel-cache
  .turbo
  .svelte-kit
  .angular
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log() { printf '[discover] %s\n' "$*" >&2; }

die() { printf '[discover] FATAL: %s\n' "$*" >&2; exit 1; }

# JSON string escape: newlines/quotes/backslashes/control chars.
json_escape() {
  local s="$1"
  # Escape backslash first, then double-quote, then control chars.
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

# Build the find -prune argument list.
build_prune_expr() {
  local first=1
  printf '('
  for name in "${PRUNE_NAMES[@]}"; do
    if (( first )); then
      first=0
    else
      printf ' -o '
    fi
    printf -- '-name %q' "$name"
  done
  printf ' )'
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

command -v git  >/dev/null 2>&1 || die "git not on PATH"
command -v find >/dev/null 2>&1 || die "find not on PATH"
command -v awk  >/dev/null 2>&1 || die "awk not on PATH"

[[ -d "$ROOT" ]] || die "ROOT does not exist: $ROOT"

log "scanning root:  $ROOT"
log "max depth:      $MAX_DEPTH"
log "prune names:    ${#PRUNE_NAMES[@]} entries"

# ---------------------------------------------------------------------------
# Walk
# ---------------------------------------------------------------------------
# We look for directories literally named ".git" (both top-level repos and
# submodules). Bare repos (*.git without a parent .git dir) are also picked
# up via the second find invocation.

PRUNE_EXPR="$(build_prune_expr)"

# shellcheck disable=SC2086
mapfile -t GIT_DIRS < <(
  eval find \"\$ROOT\" -maxdepth \"\$MAX_DEPTH\" \
    -type d $PRUNE_EXPR -prune -o \
    -type d -name .git -print 2>/dev/null
)

log "found ${#GIT_DIRS[@]} .git directories"

# ---------------------------------------------------------------------------
# Emit JSON array
# ---------------------------------------------------------------------------

printf '[\n'

first_entry=1
for gitdir in "${GIT_DIRS[@]}"; do
  # Repo working tree is the parent of .git (for normal repos). For a
  # detached .git file (worktree/submodule) we still point at the parent.
  repo="$(dirname "$gitdir")"

  # Skip if git itself refuses to recognise it.
  if ! git -C "$repo" rev-parse --git-dir >/dev/null 2>&1; then
    log "skip (not a git repo): $repo"
    continue
  fi

  # --- default branch / HEAD ----------------------------------------------
  head_ref="$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null || printf 'UNKNOWN')"
  head_sha="$(git -C "$repo" rev-parse --short HEAD 2>/dev/null || printf 'UNKNOWN')"

  # --- cleanliness --------------------------------------------------------
  uncommitted=0
  if status_out="$(git -C "$repo" status --porcelain 2>/dev/null)"; then
    if [[ -n "$status_out" ]]; then
      uncommitted="$(printf '%s\n' "$status_out" | awk 'END { print NR }')"
    fi
  fi
  clean_bool="true"
  (( uncommitted > 0 )) && clean_bool="false"

  # --- remotes ------------------------------------------------------------
  # `git remote -v` prints two lines per remote (fetch+push); dedupe on name.
  declare -A REMOTES=()
  while IFS=$'\t ' read -r rname rurl rtype; do
    [[ -z "${rname:-}" ]] && continue
    # Only record the fetch URL; push URL typically matches.
    if [[ "$rtype" == "(fetch)" || -z "${REMOTES[$rname]:-}" ]]; then
      REMOTES["$rname"]="$rurl"
    fi
  done < <(git -C "$repo" remote -v 2>/dev/null | awk '{print $1"\t"$2"\t"$3}')

  # Build the remotes JSON object.
  remotes_json=""
  r_first=1
  for rname in "${!REMOTES[@]}"; do
    esc_name="$(json_escape "$rname")"
    esc_url="$(json_escape "${REMOTES[$rname]}")"
    if (( r_first )); then
      r_first=0
    else
      remotes_json+=", "
    fi
    remotes_json+="\"${esc_name}\": \"${esc_url}\""
  done
  unset REMOTES

  # --- path normalization -------------------------------------------------
  # Keep the /c/Users/... form (Git-Bash/WSL friendly).
  esc_path="$(json_escape "$repo")"
  esc_head_ref="$(json_escape "$head_ref")"
  esc_head_sha="$(json_escape "$head_sha")"

  # --- emit --------------------------------------------------------------
  if (( first_entry )); then
    first_entry=0
  else
    printf ',\n'
  fi

  printf '  {\n'
  printf '    "path": "%s",\n'                 "$esc_path"
  printf '    "remotes": {%s},\n'              "$remotes_json"
  printf '    "default_branch": "%s",\n'       "$esc_head_ref"
  printf '    "head": "%s",\n'                 "$esc_head_sha"
  printf '    "clean": %s,\n'                  "$clean_bool"
  printf '    "uncommitted_files": %d\n'       "$uncommitted"
  printf '  }'
done

printf '\n]\n'

log "done. %d repos emitted." "$(( ${#GIT_DIRS[@]} ))"
