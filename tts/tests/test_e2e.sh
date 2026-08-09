#!/usr/bin/env bash
# E2E smoke test for TTS pipeline (Task 2)
# - verifies TTS sidecar health (direct + via letta-server)
# - verifies speak_text is attached to the agent
# - sends a trigger message ("скажи привет") and confirms the agent
#   called speak_text and got audio_base64 back
#
# Usage: LETTA_API_KEY=... ./test_e2e.sh
#
# Exit code: 0 on success, non-zero on any failed check.
set -euo pipefail

LETTA_BASE_URL="${LETTA_BASE_URL:-http://localhost:8283}"
AGENT_ID="${AGENT_ID:-agent-d622b194-88c6-4972-8421-fda92c1753a0}"
TTS_PORT="${TTS_PORT:-8000}"
PROBE_TEXT="${PROBE_TEXT:-Маша, скажи привет тест e2e}"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

echo "1) TTS sidecar /health (direct)"
HEALTH=$(curl -fsS "http://localhost:${TTS_PORT}/health") || fail "tts direct /health unreachable"
echo "$HEALTH" | grep -q '"status":"ok"' || fail "tts /health did not return ok: $HEALTH"
ok "tts direct /health -> $HEALTH"

echo "2) TTS sidecar reachable from letta-server (http://tts:${TTS_PORT})"
FROM_SERVER=$(cd /home/katya/letta && docker compose exec -T letta-server \
    bash -c "curl -fsS http://tts:${TTS_PORT}/health") || fail "tts not reachable from letta-server"
echo "$FROM_SERVER" | grep -q '"status":"ok"' || fail "tts /health from letta-server not ok: $FROM_SERVER"
ok "letta-server can reach tts sidecar"

echo "3) Agent has speak_text tool"
TOOLS_JSON=$(curl -fsS "${LETTA_BASE_URL}/v1/agents/${AGENT_ID}" \
    -H "Authorization: Bearer ${LETTA_API_KEY}")
echo "$TOOLS_JSON" | python3 -c "
import json,sys
d=json.load(sys.stdin)
names=[t['name'] for t in d.get('tools',[])]
assert 'speak_text' in names, f'speak_text missing from agent tools: {names}'
print('  tools:', sorted(names))
" || fail "speak_text not in agent tools"
ok "speak_text is attached to agent"

echo "4) send trigger message and check tool call"
python3 - <<PYEOF > /tmp/tts_e2e_req.json
import json
print(json.dumps({
    "messages": [{"role": "user", "content": "${PROBE_TEXT}"}],
    "max_steps": 8,
    "include_return_message_types": ["assistant_message", "tool_call_message", "tool_return_message"]
}, ensure_ascii=False))
PYEOF

RESP=$(curl -fsS -X POST "${LETTA_BASE_URL}/v1/agents/${AGENT_ID}/messages" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" \
    --data-binary @/tmp/tts_e2e_req.json) || fail "POST /messages failed"
echo "$RESP" > /tmp/tts_e2e_resp.json
echo "  /messages response: ${#RESP} bytes"

python3 - <<'PYEOF' || fail "tool call / return assertions failed"
import json
d = json.load(open("/tmp/tts_e2e_resp.json"))
msgs = d.get("messages", [])
calls = [m for m in msgs if m.get("message_type") == "tool_call_message"]
rets  = [m for m in msgs if m.get("message_type") == "tool_return_message"]
speak_calls = [c for c in calls if (c.get("tool_call") or {}).get("name") == "speak_text"]
assert speak_calls, f"no speak_text tool_call in messages: {[(m.get('message_type'), (m.get('tool_call') or {}).get('name')) for m in msgs]}"
args = speak_calls[0]["tool_call"].get("arguments", "")
if isinstance(args, str):
    args = json.loads(args)
assert args.get("text"), f"speak_text called with empty text: {args}"
print(f"  speak_text called with text={args.get('text')!r} voice={args.get('voice','')!r}")
assert rets, "no tool_return_message"
speak_ret = next((r for r in rets if (r.get("tool_return") or "")), None)
assert speak_ret, "no tool_return for speak_text"
rv = json.loads(speak_ret["tool_return"]) if isinstance(speak_ret["tool_return"], str) else speak_ret["tool_return"]
assert "audio_base64" in rv, f"no audio_base64 in return: keys={list(rv.keys())}"
assert len(rv["audio_base64"]) > 100, f"audio_base64 too short: {len(rv['audio_base64'])}"
print(f"  audio_base64 length={len(rv['audio_base64'])} filename={rv.get('filename')} duration_sec={rv.get('duration_sec')} synthesis_ms={rv.get('synthesis_ms')}")
print("E2E: PASS")
PYEOF

echo "ALL E2E CHECKS PASSED"
