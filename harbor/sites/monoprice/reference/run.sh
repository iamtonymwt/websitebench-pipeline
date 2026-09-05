#!/usr/bin/env bash
# Start the monoprice clone as Harbor's reference implementation.
#
# The clone is *located*, not copied. Its asset tree is 2.6 GB and its frozen
# pages another 224 MB; duplicating that into the reference tree for every run
# would be absurd. If it cannot be found, this exits non-zero with the reason
# rather than starting something that will answer wrongly.
#
# Harbor supplies HOST, PORT and WEBSITEBENCH_DATA_DIR. The database filename is
# fixed by the site backend's runtime contract -- it refuses a file that is not
# named <site>.sqlite3 -- so the data directory is used, not an invented name.
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8080}"
DATA_DIR="${WEBSITEBENCH_DATA_DIR:-${DATA_DIR:-}}"

find_clone() {
  if [[ -n "${WEBSITEBENCH_CLONE_DIR:-}" && -f "${WEBSITEBENCH_CLONE_DIR}/clone/app.py" ]]; then
    printf '%s\n' "${WEBSITEBENCH_CLONE_DIR}"
    return 0
  fi
  local here repo
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  # harbor/sites/monoprice/reference -> repository root
  repo="$(cd "${here}/../../../.." && pwd)"
  if [[ -f "${repo}/materials/monoprice/clone/app.py" ]]; then
    printf '%s\n' "${repo}/materials/monoprice"
    return 0
  fi
  return 1
}

if ! SITE_DIR="$(find_clone)"; then
  echo "reference/run.sh: cannot locate the monoprice clone." >&2
  echo "  Set WEBSITEBENCH_CLONE_DIR to the directory containing clone/app.py," >&2
  echo "  or run from a checkout with materials/monoprice/ present." >&2
  exit 1
fi

if [[ -z "${DATA_DIR}" ]]; then
  DATA_DIR="$(mktemp -d)"
fi
mkdir -p "${DATA_DIR}"

PYTHON="${WEBSITEBENCH_PYTHON:-python3}"
export WEBSITEBENCH_SITE_BACKEND_DATABASE="${DATA_DIR}/monoprice.sqlite3"
export TZ="${TZ:-UTC}"

cd "${SITE_DIR}"
exec "${PYTHON}" -m uvicorn app:app \
  --app-dir clone --host "${HOST}" --port "${PORT}" --log-level warning
