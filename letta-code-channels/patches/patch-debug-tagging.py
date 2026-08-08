"""TEMPORARY DEBUG PATCH: append [model: secretary-model | latency: Xs] to outgoing
messages for the two user chat_ids.

REMOVAL: delete this file and remove the invocation from Dockerfile, then rebuild.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()

WHITELIST = ("380975907324", "322910508")
MODEL_NAME = "secretary-model"
TAG_MARKER = "[model:"

# A) Record inbound timestamp in handleInboundMessage
old_a = (
    "  async function handleInboundMessage(msg) {\n"
    "    const accountId = msg.accountId ?? LEGACY_CHANNEL_ACCOUNT_ID;"
)
new_a = (
    "  async function handleInboundMessage(msg) {\n"
    "    try {\n"
    "      const __tsMap = (globalThis.__inboundTs ||= new Map());\n"
    "      if (msg && msg.chatId) __tsMap.set(String(msg.chatId), Date.now());\n"
    "    } catch {}\n"
    "    const accountId = msg.accountId ?? LEGACY_CHANNEL_ACCOUNT_ID;"
)
if old_a not in s:
    raise SystemExit("ERROR: handleInboundMessage not found (already patched or bndl changed)")
s = s.replace(old_a, new_a, 1)

# B) Append tag in buildMessageChannelRequest
old_b = (
    "function buildMessageChannelRequest(input, chatId, threadId) {\n"
    "  return {\n"
    "    action: input.action,\n"
    "    channel: input.channel,\n"
    "    chatId,\n"
    "    message: input.message,\n"
)
new_b = (
    "function buildMessageChannelRequest(input, chatId, threadId) {\n"
    "  try {\n"
    f"    const __whitelist = new Set({list(WHITELIST)!r});\n"
    "    const __tsMap = globalThis.__inboundTs;\n"
    f"    if (input && typeof input.message === \"string\" && input.action !== \"react\" && input.action !== \"remove\" && input.action !== \"download-file\" && !input.message.includes({TAG_MARKER!r}) && __whitelist.has(String(chatId)) && __tsMap && __tsMap.has(String(chatId))) {{\n"
    f"      const __lat = ((Date.now() - __tsMap.get(String(chatId))) / 1000).toFixed(1);\n"
    f"      input.message = input.message + \"\\n\\n[model: {MODEL_NAME} | latency: \" + __lat + \"s]\";\n"
    "      __tsMap.delete(String(chatId));\n"
    "    }\n"
    "  } catch {}\n"
    "  return {\n"
    "    action: input.action,\n"
    "    channel: input.channel,\n"
    "    chatId,\n"
    "    message: input.message,\n"
)
if old_b not in s:
    raise SystemExit("ERROR: buildMessageChannelRequest not found (already patched or bndl changed)")
s = s.replace(old_b, new_b, 1)

p.write_text(s)
print("OK: debug-tagging patch applied")
