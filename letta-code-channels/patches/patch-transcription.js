const fs = require("fs");

const file = "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js";

let source = fs.readFileSync(file, "utf8");

const oldCode = `var OPENAI_TRANSCRIPTION_API_URL = "https://api.openai.com/v1/audio/transcriptions", OPENAI_TRANSCRIPTION_MODEL = "gpt-4o-transcribe", TRANSCRIPTION_TIMEOUT_MS = 30000, OPENAI_SUPPORTED_AUDIO_EXTENSIONS;`;

const newCode = `var OPENAI_TRANSCRIPTION_API_URL = \`\${process.env.OPENAI_TRANSCRIPTION_BASE_URL || process.env.OPENAI_BASE_URL || "https://api.openai.com/v1"}/audio/transcriptions\`, OPENAI_TRANSCRIPTION_MODEL = process.env.OPENAI_TRANSCRIPTION_MODEL || "gpt-4o-transcribe", TRANSCRIPTION_TIMEOUT_MS = 30000, OPENAI_SUPPORTED_AUDIO_EXTENSIONS;`;

if (!source.includes(oldCode)) {
  throw new Error("Target transcription constants not found; Letta Code bundle may have changed.");
}

source = source.replace(oldCode, newCode);

fs.writeFileSync(file, source);

console.log("Patched Letta Code transcription endpoint and model.");
