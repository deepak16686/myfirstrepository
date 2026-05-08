#!/usr/bin/env bash
# Diff variable NAMES (not values) between the root and backend .env.example.
# Run locally — guardrails in the assistant block it from reading .env.* paths.
#
# Output:
#   /tmp/env-root-keys.txt     — sorted unique variables from root .env.example
#   /tmp/env-backend-keys.txt  — sorted unique variables from devops-tools-backend/.env.example
#   /tmp/env-only-in-root.txt  — variables defined only in root (candidates to merge)
#   /tmp/env-only-in-backend.txt — variables defined only in backend (usually fine)
#   /tmp/env-in-both.txt       — variables present in both (check values match)
#
# Usage:
#   bash infrastructure/scripts/ops/diff-env-example.sh
#   cat /tmp/env-only-in-root.txt     # decide which to copy over
#
# Safety: this script prints ONLY variable names, never values.

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

ROOT=".env.example"
BACKEND="services/devops-tools-backend/.env.example"

[[ -f "$ROOT"    ]] || { echo "missing: $ROOT"    >&2; exit 1; }
[[ -f "$BACKEND" ]] || { echo "missing: $BACKEND" >&2; exit 1; }

extract_keys() {
  awk -F= '/^[A-Z_][A-Z0-9_]*=/ {print $1}' "$1" | sort -u
}

extract_keys "$ROOT"    > /tmp/env-root-keys.txt
extract_keys "$BACKEND" > /tmp/env-backend-keys.txt

comm -23 /tmp/env-root-keys.txt /tmp/env-backend-keys.txt > /tmp/env-only-in-root.txt
comm -13 /tmp/env-root-keys.txt /tmp/env-backend-keys.txt > /tmp/env-only-in-backend.txt
comm -12 /tmp/env-root-keys.txt /tmp/env-backend-keys.txt > /tmp/env-in-both.txt

printf "%-24s %s\n" "root .env.example keys:"        "$(wc -l < /tmp/env-root-keys.txt)"
printf "%-24s %s\n" "backend .env.example keys:"     "$(wc -l < /tmp/env-backend-keys.txt)"
printf "%-24s %s\n" "only in root (to consider):"    "$(wc -l < /tmp/env-only-in-root.txt)"
printf "%-24s %s\n" "only in backend:"               "$(wc -l < /tmp/env-only-in-backend.txt)"
printf "%-24s %s\n" "in both (check for drift):"     "$(wc -l < /tmp/env-in-both.txt)"
echo
echo "-- keys present ONLY in root .env.example --"
cat /tmp/env-only-in-root.txt
echo
echo "Next steps:"
echo "  1. Inspect each key in /tmp/env-only-in-root.txt and decide: copy to backend, or drop."
echo "  2. For keys in /tmp/env-in-both.txt, visually diff their values and reconcile."
echo "  3. Run 'git rm .env.example' once everything useful is migrated."
