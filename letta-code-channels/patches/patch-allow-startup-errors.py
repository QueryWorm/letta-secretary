import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()

# ChannelGateway must NOT crash the whole gateway when a single channel fails
# to start (e.g. Telegram API blocked). Always allow startup errors so the
# gateway keeps running with the channels that did start.
old = "failOnStartupError: Boolean(values2.channels),"
new = "failOnStartupError: false,"
if old not in s:
    raise SystemExit("ERROR: failOnStartupError block not found")
s = s.replace(old, new, 1)

p.write_text(s)
print("OK: allow channel startup errors patch applied")
