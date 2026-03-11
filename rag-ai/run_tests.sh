#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

SKIP_INGEST=false
SKIP_API=false
RETRIEVAL_ONLY=false

while (($# > 0)); do
  case "$1" in
    --skip-ingest)
      SKIP_INGEST=true
      ;;
    --skip-api)
      SKIP_API=true
      ;;
    --retrieval-only)
      RETRIEVAL_ONLY=true
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  ./run_tests.sh [--skip-ingest] [--skip-api] [--retrieval-only]
EOF
      exit 0
      ;;
    *)
      printf '[ERROR] Unknown argument: %s\n' "$1" >&2
      exit 1
      ;;
  esac
  shift
done

PYTHON_BIN="$(command -v python3 || command -v python || true)"
[[ -n "${PYTHON_BIN}" ]] || { printf '[ERROR] Python 3 is required.\n' >&2; exit 1; }

CHROMADB_URL="${CHROMADB_URL:-http://localhost:8005}"
API_URL="${GENERATOR_API_URL:-http://localhost:8080}"
API_PID=""

ensure_module() {
  local module="$1"
  local package="$2"

  if ! "${PYTHON_BIN}" -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('${module}') else 1)" >/dev/null 2>&1; then
    printf '[INFO] Installing Python package: %s\n' "${package}"
    "${PYTHON_BIN}" -m pip install --quiet "${package}"
  fi
}

cleanup() {
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" >/dev/null 2>&1; then
    printf '[INFO] Stopping generator API (pid=%s)\n' "${API_PID}"
    kill "${API_PID}" >/dev/null 2>&1 || true
    wait "${API_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT

printf '======================================================================\n'
printf 'AI Dockerfile & GitLab CI Generator - Test Runner\n'
printf '======================================================================\n'

printf '\n[STEP 0] Checking Python dependencies...\n'
"${PYTHON_BIN}" --version
ensure_module chromadb chromadb
ensure_module fastapi fastapi
ensure_module uvicorn uvicorn
ensure_module requests requests
ensure_module yaml pyyaml

printf '\n[STEP 1] Checking ChromaDB connectivity at %s ...\n' "${CHROMADB_URL}"
if curl -fsS --max-time 5 "${CHROMADB_URL}/api/v2/heartbeat" >/dev/null; then
  printf '  [OK] ChromaDB is reachable\n'
else
  printf '  [ERROR] ChromaDB is not reachable at %s\n' "${CHROMADB_URL}" >&2
  exit 1
fi

if [[ "${SKIP_INGEST}" == false ]]; then
  printf '\n[STEP 2] Ingesting templates into ChromaDB...\n'
  "${PYTHON_BIN}" create_collections.py
  "${PYTHON_BIN}" ingest_templates.py
  printf '  [OK] Template ingestion completed\n'
else
  printf '\n[STEP 2] Skipping ingestion\n'
fi

printf '\n[STEP 3] Running ChromaDB retrieval tests...\n'
if ! "${PYTHON_BIN}" test_retrieval.py; then
  printf '  [WARN] Some retrieval tests failed\n' >&2
fi

if [[ "${RETRIEVAL_ONLY}" == true ]]; then
  printf '\n[DONE] Retrieval-only mode requested.\n'
  exit 0
fi

if [[ "${SKIP_API}" == false ]]; then
  printf '\n[STEP 4] Ensuring generator API is running at %s ...\n' "${API_URL}"
  if curl -fsS --max-time 3 "${API_URL}/" >/dev/null 2>&1; then
    printf '  [OK] API already running\n'
  else
    mkdir -p test_output
    "${PYTHON_BIN}" generator_api.py > test_output/api_stdout.log 2> test_output/api_stderr.log &
    API_PID="$!"
    sleep 3
    curl -fsS --max-time 5 "${API_URL}/" >/dev/null
    printf '  [OK] API started (pid=%s)\n' "${API_PID}"
  fi
else
  printf '\n[STEP 4] Skipping API startup\n'
fi

printf '\n[STEP 5] Running full test suite...\n'
if "${PYTHON_BIN}" test_generator.py; then
  printf '\n======================================================================\n'
  printf 'ALL TESTS PASSED\n'
  printf '======================================================================\n'
else
  printf '\n======================================================================\n'
  printf 'SOME TESTS FAILED - check test_output/test_results.json\n'
  printf '======================================================================\n'
  exit 1
fi
