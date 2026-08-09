FROM node:22-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv make g++ git curl wget jq ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/tts-venv \
    && /opt/tts-venv/bin/pip install --no-cache-dir edge-tts \
    && ln -s /opt/tts-venv/bin/edge-tts /usr/local/bin/edge-tts

RUN npm install -g @letta-ai/letta-code@0.30.3 \
    && python3 - <<'PY'
from pathlib import Path

p = Path("/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()

old = 'var OPENAI_TRANSCRIPTION_API_URL = "https://api.openai.com/v1/audio/transcriptions", OPENAI_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"'

new = 'var OPENAI_TRANSCRIPTION_API_URL = process.env.OPENAI_TRANSCRIPTION_BASE_URL ? process.env.OPENAI_TRANSCRIPTION_BASE_URL.replace(/\\/$/, "") + "/v1/audio/transcriptions" : "https://api.openai.com/v1/audio/transcriptions", OPENAI_TRANSCRIPTION_MODEL = process.env.OPENAI_TRANSCRIPTION_MODEL || "gpt-4o-transcribe"'

if old not in s:
    raise SystemExit("ERROR: transcription constants not found in Letta Code 0.30.3")

p.write_text(s.replace(old, new, 1))
print("OK: transcription endpoint/model patched")
PY

RUN python3 - <<'PY'
from pathlib import Path
p = Path("/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()
old = '  await writeFile7(localPath, buffer);\n  attachment.localPath = localPath;\n  if (isVoice && params.transcribeVoice) {'
new = '  await writeFile7(localPath, buffer);\n  attachment.localPath = localPath;\n  if (candidate.attachmentKind === "image") {\n    attachment.imageDataBase64 = buffer.toString("base64");\n  }\n  if (isVoice && params.transcribeVoice) {'
if old not in s:
    raise SystemExit("ERROR: whatsapp attachment localPath block not found in Letta Code 0.30.3")
p.write_text(s.replace(old, new, 1))
print("OK: whatsapp image imageDataBase64 patch applied")
PY

COPY patches/patch-gateway-send.py /tmp/patch-gateway-send.py
RUN python3 /tmp/patch-gateway-send.py && rm /tmp/patch-gateway-send.py

COPY patches/patch-turn-error.py /tmp/patch-turn-error.py
RUN python3 /tmp/patch-turn-error.py && rm /tmp/patch-turn-error.py

COPY patches/patch-debug-tagging.py /tmp/patch-debug-tagging.py
RUN python3 /tmp/patch-debug-tagging.py && rm /tmp/patch-debug-tagging.py

COPY patches/patch-allow-startup-errors.py /tmp/patch-allow-startup-errors.py
RUN python3 /tmp/patch-allow-startup-errors.py && rm /tmp/patch-allow-startup-errors.py

COPY patches/patch-channel-retry.py /tmp/patch-channel-retry.py
RUN python3 /tmp/patch-channel-retry.py && rm /tmp/patch-channel-retry.py

WORKDIR /root

VOLUME ["/root/.letta"]

ENTRYPOINT ["letta"]
