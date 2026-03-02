#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
APP_PY="$REPO_ROOT/app.py"
DEFAULT_PYTHON="$REPO_ROOT/.venv/bin/python"
PYTHON_EXE="${RTX_PYTHON_EXE:-$DEFAULT_PYTHON}"

if [ ! -f "$APP_PY" ]; then
    echo "Missing application entrypoint: $APP_PY" >&2
    exit 1
fi

if [ ! -x "$PYTHON_EXE" ]; then
    echo "Python executable is not available: $PYTHON_EXE" >&2
    echo "Set RTX_PYTHON_EXE or create $DEFAULT_PYTHON before starting the service." >&2
    exit 1
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "nvidia-smi is required on PATH but was not found." >&2
    exit 1
fi

if ! "$PYTHON_EXE" -c "import flask, dotenv, waitress" >/dev/null 2>&1; then
    echo "Python dependencies are missing for $PYTHON_EXE. Install requirements.txt first." >&2
    exit 1
fi

mkdir -p "$REPO_ROOT/logs"
cd "$REPO_ROOT"

exec "$PYTHON_EXE" "$APP_PY"
