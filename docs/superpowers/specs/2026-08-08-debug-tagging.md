# Debug Tagging in Outgoing Messages — Design

**Date:** 2026-08-08
**Status:** approved
**Scope:** temporary debug feature, will be removed

## Goal

Append a small debug tag to outgoing agent messages in WhatsApp and Telegram,
showing which `model_name` and how much time elapsed between inbound user
message and outgoing MessageChannel.

## Why

Currently the user has no way to see from the chat itself how long the agent
took to answer or which logical model answered. LiteLLM logs show real
provider models, but the user wants the tag inline for quick eyeballing.

## Tag format

```
[model: secretary-model | latency: 2.4s]
```

- `model`: the `model_name` from `parentScope` (currently always
  `secretary-model` — the LiteLLM alias; the user can map it to real providers
  in their head from `litellm-config.yaml`).
- `latency`: seconds between the moment the inbound user message arrived in
  the channel and the moment the outgoing `MessageChannel` is being dispatched.
  Format: `<X.Ys>` with one decimal.

The tag is appended after a blank line at the end of the message body.

## Scope of effect

- **Only** the two chat_ids belonging to the user:
  - WhatsApp: `380975907324`
  - Telegram: `322910508`
- All other recipients (e.g. cron to other addresses, future channels) are
  untouched.

## Architecture

Single patch in JS bundle `letta-code-channels/letta.js`. No new IPC, no
shared volume, no `letta-server` changes.

## Data flow

1. **Inbound** — `handleInboundMessage` in the channel adapter records
   `Date.now()` into an in-memory map keyed by `chatId`.
2. **Outbound** — `executeMessageChannel` (or directly in
   `buildMessageChannelRequest`) reads the timestamp for the target
   `chatId`, computes the delta, and appends the tag to the message body if
   the `chatId` is in the user's whitelist.

## Components

### Patch file

- `letta-code-channels/patches/patch-debug-tagging.py`
  - Patches `handleInboundMessage` to record `globalThis.__inboundTs[chatId] = Date.now()`
  - Patches `buildMessageChannelRequest` to read the timestamp and append the tag
  - Idempotent: detects already-applied state and bails out
  - Backs up original to `letta.js.bak` before patching

### Bundle location

- `/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js` (inside the
  `letta-code-channels` container)
- The patch script accepts the path as argv[1], defaulting to the above.

### Docker build

- The patch is applied **at container start**, not at image build. This is
  consistent with existing patches (`patch-gateway-send.py`,
  `patch-turn-error.py`).
- Patch script is mounted into the container or baked into the image. The
  current `Dockerfile` already runs all patches; add the new one there.

## Error handling

- If `__inboundTs[chatId]` is missing (e.g. proactive cron with no prior
  inbound), no tag is appended.
- If `parentScope` is missing, fall back to `model = "secretary-model"`
  (which is what the user wants anyway).
- If the message already contains `[model:` (idempotency), do not append
  again. This protects against double-send scenarios.

## Testing

- Send "ping" to WhatsApp and Telegram from the user's accounts.
- Confirm the response contains the tag with a sensible latency value.
- Send two messages in a row — confirm each gets its own correct latency
  (not a cumulative one).
- Send a cron reminder — confirm the tag is **not** appended (cron → not in
  the chat whitelist in the current design).

## Removal

This is a temporary debug feature. To remove:

1. Delete `letta-code-channels/patches/patch-debug-tagging.py`.
2. Remove the patch invocation from `Dockerfile`.
3. Rebuild the `letta-code-channels` image.
4. The original bundle (pre-patch) is at
   `letta.js.bak` inside the container; or just `docker compose pull`
   the base image again.

No production data depends on the tag.
