#!/usr/bin/env bash
# Cron wrapper for ingest pipeline.
# Reads configuration from project .env (if present) or environment.
#
# Crontab entry:
#   0 2 * * * /home/katya/letta/scripts/run_cron.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$PROJECT_DIR/.env"
    set +a
fi

VAULT_PATH="${INGEST_VAULT_PATH:-/home/katya/ObsidianVault}"
DAYS="${INGEST_DAYS:-90}"
SOURCE_NAME="${INGEST_SOURCE_NAME:-personal_kb}"
CREATE_FLAG=""
if [ "${INGEST_RECREATE:-0}" = "1" ]; then
    CREATE_FLAG="--create"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PATH="${VENV_PATH:-/tmp/ingest_venv}"

if [ -x "$VENV_PATH/bin/python" ]; then
    PYTHON_BIN="$VENV_PATH/bin/python"
fi

cd "$PROJECT_DIR"
PYTHONPATH="$PROJECT_DIR" "$PYTHON_BIN" "$SCRIPT_DIR/ingest.py" \
    --vault "$VAULT_PATH" \
    --days "$DAYS" \
    --source "$SOURCE_NAME" \
    $CREATE_FLAG
