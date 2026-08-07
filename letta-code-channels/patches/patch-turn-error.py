import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()

# A) Terminal LLM loop error: include the error text in turn_finished.
#    Without this, turn_finished is emitted before the loop_error delta, so
#    ChannelGateway finalizes the turn with an empty error and the user never
#    receives a failure message when every model provider fails.
old_a = (
    '        const errorMessage2 = errorDetail2 || `Unexpected stop reason: ${stopReason}`;\n'
    '        const terminalRunId = runId || runtime.activeRunId || runErrorInfo2?.run_id;\n'
    '        const transition = finishTurn({\n'
    '          stopReason: effectiveStopReason,\n'
    '          agentId,\n'
    '          conversationId\n'
    '        });'
)
new_a = (
    '        const errorMessage2 = errorDetail2 || `Unexpected stop reason: ${stopReason}`;\n'
    '        const terminalRunId = runId || runtime.activeRunId || runErrorInfo2?.run_id;\n'
    '        const transition = finishTurn({\n'
    '          stopReason: effectiveStopReason,\n'
    '          error: errorMessage2,\n'
    '          agentId,\n'
    '          conversationId\n'
    '        });'
)
if old_a not in s:
    raise SystemExit("ERROR: terminal loop error finishTurn block not found")
s = s.replace(old_a, new_a, 1)

# B) Uncaught turn processing error: same fix for the outer catch.
old_b = (
    '    const errorMessage2 = error54 instanceof Error ? error54.message : String(error54);\n'
    '    const terminalRunId = runtime.activeRunId;\n'
    '    const transition = finishTurn({\n'
    '      stopReason: "error",\n'
    '      agentId: agentId || null,\n'
    '      conversationId\n'
    '    });'
)
new_b = (
    '    const errorMessage2 = error54 instanceof Error ? error54.message : String(error54);\n'
    '    const terminalRunId = runtime.activeRunId;\n'
    '    const transition = finishTurn({\n'
    '      stopReason: "error",\n'
    '      error: errorMessage2,\n'
    '      agentId: agentId || null,\n'
    '      conversationId\n'
    '    });'
)
if old_b not in s:
    raise SystemExit("ERROR: catch finishTurn block not found")
s = s.replace(old_b, new_b, 1)

# C) ChannelGateway: do NOT finalize the turn on a stream stop_reason of
#    llm_api_error. The harness retries providers and emits turn_finished with
#    the real error only after exhausting retries; finalizing on the first
#    stream stop_reason cleared active first, so the later turn_finished (with
#    the error text) was dropped and the user got no failure message.
old_c = (
    '    const stopReason = stopReasonFromDelta(message);\n'
    '    if (!stopReason)\n'
    '      return;\n'
    '    if (stopReason === "requires_approval") {'
)
new_c = (
    '    const stopReason = stopReasonFromDelta(message);\n'
    '    if (!stopReason)\n'
    '      return;\n'
    '    if (stopReason === "llm_api_error") {\n'
    '      return;\n'
    '    }\n'
    '    if (stopReason === "requires_approval") {'
)
if old_c not in s:
    raise SystemExit("ERROR: gateway handleStreamDelta block not found")
s = s.replace(old_c, new_c, 1)

p.write_text(s)
print("OK: turn_finished error propagation + gateway llm_api_error hold patches applied")
