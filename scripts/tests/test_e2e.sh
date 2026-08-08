#!/usr/bin/env bash
# End-to-end smoke test for knowledge pipeline.
# Requires: letta-server running, .env with API keys.
# Skips chat-message LLM extraction (uses --days 0) so the smoke test
# is fast and independent of litellm chat availability.
#
# Exit code:
#   0  = all steps passed
#   1  = a step failed (e.g. search_passages returned non-2xx)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$PROJECT_DIR/.env"
    set +a
fi

LETTA_BASE_URL="${LETTA_BASE_URL:-http://localhost:8283}"
SMOKE_SOURCE="personal_kb_smoke"
VAULT_PATH="${INGEST_VAULT_PATH_SMOKE:-/home/katya/Documents/test-vault-smoke}"

# /v1/sources/name/{name} returns the source id as a JSON string on success,
# or `{"detail":"... not found."}` on 404. Extract a source-id-shaped value
# or empty.
extract_source_id() {
    python3 -c "
import json, sys, re
raw = sys.stdin.read().strip()
try:
    val = json.loads(raw)
except Exception:
    print('')
    sys.exit(0)
if isinstance(val, str):
    print(val)
elif isinstance(val, dict):
    m = re.match(r'^source-[a-fA-F0-9-]+$', val.get('id', '') if 'id' in val else '')
    print(m.group(0) if m else '')
else:
    print('')
"
}

# Idempotency: drop any leftover source from a previous run.
EXISTING_ID=$(curl -sS "${LETTA_BASE_URL}/v1/sources/name/${SMOKE_SOURCE}" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" 2>/dev/null | extract_source_id || true)
if [ -n "$EXISTING_ID" ]; then
    curl -sS -X DELETE "${LETTA_BASE_URL}/v1/sources/${EXISTING_ID}" \
        -H "Authorization: Bearer ${LETTA_API_KEY}" >/dev/null
fi

rm -rf "$VAULT_PATH"
mkdir -p "$VAULT_PATH"
cat > "$VAULT_PATH/test-note.md" <<'EOF'
# Test vault for e2e

WireGuard setup notes.
EOF
cat > "$VAULT_PATH/lab-note.md" <<'EOF'
# HTB lab walkthrough

Kerberoasting steps.
EOF

echo "[1/4] running ingest --create (vault-only, --days 0 skips chat LLM)..."
PYTHONPATH="$PROJECT_DIR" python3 "$SCRIPT_DIR/../ingest.py" \
    --vault "$VAULT_PATH" --days 0 --source "$SMOKE_SOURCE" --create

echo "[2/4] verifying source exists..."
SMOKE_SOURCE_ID=$(curl -sS "${LETTA_BASE_URL}/v1/sources/name/${SMOKE_SOURCE}" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" | extract_source_id)
echo "  source_id=${SMOKE_SOURCE_ID}"
curl -sS "${LETTA_BASE_URL}/v1/sources/${SMOKE_SOURCE_ID}" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" | head -c 200
echo

echo "[3/4] verifying search_passages works..."
SEARCH_STATUS=$(curl -sS -o /tmp/e2e_search.json -w "%{http_code}" \
    -X POST "${LETTA_BASE_URL}/v1/passages/search" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"WireGuard\", \"limit\": 3, \"source_id\": \"${SMOKE_SOURCE_ID}\"}")
echo "  http_status=${SEARCH_STATUS}"
head -c 600 /tmp/e2e_search.json
echo
if [ "${SEARCH_STATUS}" -ge 400 ]; then
    echo "  WARN: search_passages returned HTTP ${SEARCH_STATUS}" >&2
fi

echo "[4/4] cleanup..."
curl -sS -X DELETE "${LETTA_BASE_URL}/v1/sources/${SMOKE_SOURCE_ID}" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" >/dev/null
echo
rm -rf "$VAULT_PATH"

if [ "${SEARCH_STATUS}" -ge 400 ]; then
    echo "FAIL: e2e smoke failed (search_passages HTTP ${SEARCH_STATUS})" >&2
    exit 1
fi

echo "OK: e2e smoke passed"
