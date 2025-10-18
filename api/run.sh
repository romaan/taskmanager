#!/usr/bin/env bash

# Helper script for Async Task Manager (Django-style FastAPI layout)
# Usage:
#   ./run.sh init [--dev]
#   ./run.sh run
#   ./run.sh dev
#   ./run.sh test
#   ./run.sh clean
#   ./run.sh nuke

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/.env"
PYTHON_BIN="python"
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

activate() { source "${VENV_DIR}/bin/activate"; }
ensure_venv() {
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "Creating virtualenv at ${VENV_DIR} ..."
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
  # shellcheck disable=SC1090
  source "${VENV_DIR}/bin/activate"
  python -m pip install --upgrade pip setuptools wheel >/dev/null
}

cmd_init() {
  local dev="${1:-}"
  ensure_venv
  echo "Installing runtime requirements..."
  pip install -r "${PROJECT_DIR}/requirements.txt"
  if [[ "${dev:-}" == "--dev" ]]; then
    echo "Installing dev requirements..."
    pip install -r "${PROJECT_DIR}/requirements-dev.txt"
  fi
  echo "Done."
}

cmd_run() { ensure_venv; exec uvicorn main:app --host 0.0.0.0 --port 8000; }
cmd_dev() { ensure_venv; exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload; }

cmd_test() {
  ensure_venv
  if ! python -c "import pytest" >/dev/null 2>&1; then
    echo "pytest not found. Installing dev requirements..."
    pip install -r "${PROJECT_DIR}/requirements-dev.txt"
  fi
  pytest -v
}

cmd_clean() {
  find "${PROJECT_DIR}" -type d -name "__pycache__" -exec rm -rf {} + || true
  rm -rf "${PROJECT_DIR}/.pytest_cache" || true
  echo "Cleaned caches."
}

cmd_nuke() {
  rm -rf "${VENV_DIR}" "${PROJECT_DIR}/.pytest_cache"
  find "${PROJECT_DIR}" -type d -name "__pycache__" -exec rm -rf {} + || true
  echo "Removed env and caches."
}

usage() { sed -n '1,80p' "$0" | sed 's/^# \{0,1\}//'; }

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    init) shift; cmd_init "${@:-}";;
    run) shift; cmd_run;;
    dev) shift; cmd_dev;;
    test) shift; cmd_test;;
    clean) shift; cmd_clean;;
    nuke) shift; cmd_nuke;;
    ""|"help"|"-h"|"--help") usage;;
    *) echo "Unknown command: ${cmd}"; usage; exit 1;;
  esac
}
main "$@"
