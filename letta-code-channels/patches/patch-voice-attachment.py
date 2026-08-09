"""TEMPORARY PATCH: add audio_base64 support to MessageChannel tool.

Lets the agent (or any caller of MessageChannel) deliver TTS-synthesised
audio to a channel without first writing the bytes to disk. When the new
optional `audio_base64` parameter is provided, the bundle decodes it into
a temp file, sets `mediaPath` to that file, picks a sensible default
`filename` (`.ogg` — matches the TTS sidecar's default extension and is
the format WhatsApp voice notes expect), and schedules cleanup of the
temp file after the channel send completes.

Behaviour:
- If `audio_base64` is not provided, this patch is a no-op (the existing
  `media`/`filename`/`title` fields keep their prior meaning).
- If `audio_base64` is provided and the channel plugin's
  `describeMessageTool().actions` includes `upload-file`, the request is
  delivered as a media attachment. Telegram + WhatsApp plugins both
  report `upload-file` so this is the supported path.
- Temp file lives in `os.tmpdir()` with a `letta-tts-audio-XXXXXX.ogg`
  template. Cleanup is fire-and-forget via `setTimeout(..., 60_000)`
  with `.unref()` so it never blocks process exit.

Idempotency: detected by scanning for the marker comment
`// AUDIO_BASE64_PATCH_APPLIED` that the script inserts on first run.
If the marker is present, the script exits 0 with "already applied".
"""
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()

MARKER = "// AUDIO_BASE64_PATCH_APPLIED"
if MARKER in s:
    print("OK: audio_base64 patch already applied (marker present), no-op")
    sys.exit(0)

# A) Add `audio_base64` to the MessageChannel JSON schema.
old_a = (
    '      title: {\n'
    '        type: "string",\n'
    '        description: "Optional uploaded title override for media attachments"\n'
    '      }\n'
    '    },\n'
    '    required: ["action", "channel"],\n'
    '    additionalProperties: false\n'
    '  };\n'
    '});\n'
)
new_a = (
    '      title: {\n'
    '        type: "string",\n'
    '        description: "Optional uploaded title override for media attachments"\n'
    '      },\n'
    '      audio_base64: {\n'
    '        type: "string",\n'
    '        description: "Base64-encoded audio bytes. When provided, decoded to a temp file and sent as a media attachment (set action=upload-file). Default filename is response.ogg. Use this for TTS / voice notes; do not pass media + audio_base64 at the same time."\n'
    '      }\n'
    '    },\n'
    '    required: ["action", "channel"],\n'
    '    additionalProperties: false\n'
    '  };\n'
    '});\n'
)
if old_a not in s:
    raise SystemExit("ERROR: MessageChannel JSON schema tail not found (bundle changed?)")
s = s.replace(old_a, new_a, 1)

# B) Forward `audio_base64` in normalizeMessageChannelInput so it survives
#    until buildMessageChannelRequest.
old_b = (
    '    mediaPath: firstNonEmptyString4(input.media),\n'
    '    filename: firstNonEmptyString4(input.filename),\n'
    '    title: firstNonEmptyString4(input.title)\n'
    '  };\n'
    '}\n'
    'function buildMessageChannelRequest(input, chatId, threadId) {'
)
new_b = (
    '    mediaPath: firstNonEmptyString4(input.media),\n'
    '    filename: firstNonEmptyString4(input.filename),\n'
    '    title: firstNonEmptyString4(input.title),\n'
    '    audio_base64: firstNonEmptyString4(input.audio_base64)\n'
    '  };\n'
    '}\n'
    'function buildMessageChannelRequest(input, chatId, threadId) {'
)
if old_b not in s:
    raise SystemExit("ERROR: normalizeMessageChannelInput tail not found (bundle changed?)")
s = s.replace(old_b, new_b, 1)

# C) In buildMessageChannelRequest, decode audio_base64 to a temp file and
#    set mediaPath/filename accordingly. Cleanup is scheduled with a
#    60s unref'd timer so the file outlives the channel send but never
#    blocks process exit. We use sync writes to keep the helper sync.
#    The patch must be careful to live alongside the existing
#    debug-tagging patch which mutates `input.message` inside the
#    try/catch at the top of the function.
old_c = (
    'function buildMessageChannelRequest(input, chatId, threadId) {\n'
    '  try {\n'
    '    const __whitelist = new Set([\'380975907324\', \'380975907324@s.whatsapp.net\', \'322910508\']);\n'
    '    const __tsMap = globalThis.__inboundTs;\n'
    '    if (input && typeof input.message === "string" && input.action !== "react" && input.action !== "remove" && input.action !== "download-file" && !input.message.includes(\'[secretary-model\') && __whitelist.has(String(chatId)) && __tsMap && __tsMap.has(String(chatId))) {\n'
    '      const __lat = ((Date.now() - __tsMap.get(String(chatId))) / 1000).toFixed(1);\n'
    '      input.message = input.message + "\\n\\n[secretary-model | " + __lat + "s]";\n'
    '      __tsMap.delete(String(chatId));\n'
    '    }\n'
    '  } catch {}\n'
    '  return {\n'
    '    action: input.action,\n'
    '    channel: input.channel,\n'
    '    chatId,\n'
    '    message: input.message,\n'
    '    replyToMessageId: input.replyToMessageId,\n'
    '    threadId: threadId ?? input.threadId ?? null,\n'
    '    messageId: input.messageId,\n'
    '    attachmentId: input.attachmentId,\n'
    '    emoji: input.emoji,\n'
    '    remove: input.remove,\n'
    '    mediaPath: input.mediaPath,\n'
    '    filename: input.filename,\n'
    '    title: input.title\n'
    '  };\n'
    '}'
)
new_c = (
    'function buildMessageChannelRequest(input, chatId, threadId) {\n'
    '  try {\n'
    '    const __whitelist = new Set([\'380975907324\', \'380975907324@s.whatsapp.net\', \'322910508\']);\n'
    '    const __tsMap = globalThis.__inboundTs;\n'
    '    if (input && typeof input.message === "string" && input.action !== "react" && input.action !== "remove" && input.action !== "download-file" && !input.message.includes(\'[secretary-model\') && __whitelist.has(String(chatId)) && __tsMap && __tsMap.has(String(chatId))) {\n'
    '      const __lat = ((Date.now() - __tsMap.get(String(chatId))) / 1000).toFixed(1);\n'
    '      input.message = input.message + "\\n\\n[secretary-model | " + __lat + "s]";\n'
    '      __tsMap.delete(String(chatId));\n'
    '    }\n'
    '  } catch {}\n'
    '  ' + MARKER + '\n'
    '  if (input && typeof input.audio_base64 === "string" && input.audio_base64.length > 0) {\n'
    '    try {\n'
    '      const __buf = Buffer.from(input.audio_base64, "base64");\n'
    '      const __name = (input.filename && input.filename.trim()) || "response.ogg";\n'
    '      const __safe = __name.replace(/[^A-Za-z0-9._-]/g, "_");\n'
    '      const __tmp = require("path").join(require("os").tmpdir(), "letta-tts-audio-" + Date.now() + "-" + Math.random().toString(36).slice(2, 8) + "-" + __safe);\n'
    '      require("fs").writeFileSync(__tmp, __buf);\n'
    '      input.mediaPath = __tmp;\n'
    '      input.filename = __safe;\n'
    '      try { setTimeout(() => { try { require("fs").unlinkSync(__tmp); } catch {} }, 60000).unref(); } catch {}\n'
    '    } catch (audioErr) {\n'
    '      input.__audioDecodeError = (audioErr && audioErr.message) ? audioErr.message : String(audioErr);\n'
    '    }\n'
    '  }\n'
    '  return {\n'
    '    action: input.action,\n'
    '    channel: input.channel,\n'
    '    chatId,\n'
    '    message: input.message,\n'
    '    replyToMessageId: input.replyToMessageId,\n'
    '    threadId: threadId ?? input.threadId ?? null,\n'
    '    messageId: input.messageId,\n'
    '    attachmentId: input.attachmentId,\n'
    '    emoji: input.emoji,\n'
    '    remove: input.remove,\n'
    '    mediaPath: input.mediaPath,\n'
    '    filename: input.filename,\n'
    '    title: input.title\n'
    '  };\n'
    '}'
)
if old_c not in s:
    raise SystemExit("ERROR: buildMessageChannelRequest block not found (bundle changed or debug-tagging patch not applied?)")
s = s.replace(old_c, new_c, 1)

p.write_text(s)
print("OK: audio_base64 patch applied")
