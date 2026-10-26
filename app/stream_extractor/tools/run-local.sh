#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required to run the application locally." >&2
    exit 1
fi

VENV_DIR=""
VENV_CANDIDATES=(.venv venv .virtualenv virtualenv env ENV)

for candidate in "${VENV_CANDIDATES[@]}"; do
    if [[ -x "$candidate/bin/python" ]]; then
        VENV_DIR="$candidate"
        break
    fi
done

if [[ -z "$VENV_DIR" ]]; then
    python3 -m venv .venv
    VENV_DIR=.venv
fi

"$VENV_DIR/bin/python" -m pip install -r requirements.txt

if [[ -f .env ]]; then
    set -a
    # .env is a trusted, shell-compatible file (see .env.example).
    # shellcheck disable=SC1091
    source .env
    set +a
fi

exec "$VENV_DIR/bin/python" app.py
