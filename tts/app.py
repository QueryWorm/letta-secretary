"""TTS sidecar: edge-tts → OGG/Opus audio, with timing."""
import asyncio
import base64
import io
import time
from collections import OrderedDict
from typing import Optional

import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="TTS Sidecar", version="0.1.0")

MAX_TEXT_LEN = 5000
DEFAULT_VOICE = "ru-RU-SvetlanaNeural"
CACHE_SIZE = 50


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_TEXT_LEN * 2)
    voice: Optional[str] = DEFAULT_VOICE


class SynthesizeResponse(BaseModel):
    audio_base64: str
    filename: str
    duration_sec: float
    synthesis_ms: int
    truncated: bool = False
    text_length: int


_cache: "OrderedDict[str, SynthesizeResponse]" = OrderedDict()


def _cache_get(key: str) -> Optional[SynthesizeResponse]:
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    return None


def _cache_put(key: str, value: SynthesizeResponse) -> None:
    _cache[key] = value
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)


async def _synthesize_one(text: str, voice: str) -> bytes:
    communicate = edge_tts.Communicate(text, voice)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def _mp3_duration_estimate(mp3_bytes: bytes) -> float:
    """Rough estimate: 16kbps mono for OGG/Opus ~2KB/s. Fallback to byte count."""
    if not mp3_bytes:
        return 0.0
    return round(len(mp3_bytes) / 2000.0, 2)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/voices")
def voices() -> dict:
    """Returns short list of common voices for testing."""
    return {
        "voices": [
            "ru-RU-SvetlanaNeural",
            "ru-RU-DmitryNeural",
            "en-US-AriaNeural",
        ]
    }


@app.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(req: SynthesizeRequest) -> SynthesizeResponse:
    t_start = time.monotonic()
    truncated = False
    text = req.text
    if len(text) > MAX_TEXT_LEN:
        text = text[:MAX_TEXT_LEN]
        truncated = True
    cache_key = f"{req.voice}:{text}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        mp3_bytes = await _synthesize_one(text, req.voice)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"edge-tts synthesis failed: {e}")
    if not mp3_bytes:
        raise HTTPException(status_code=500, detail="edge-tts returned empty audio")
    t_end = time.monotonic()
    synthesis_ms = int((t_end - t_start) * 1000)
    audio_b64 = base64.b64encode(mp3_bytes).decode("ascii")
    resp = SynthesizeResponse(
        audio_base64=audio_b64,
        filename="response.ogg",
        duration_sec=_mp3_duration_estimate(mp3_bytes),
        synthesis_ms=synthesis_ms,
        truncated=truncated,
        text_length=len(req.text),
    )
    _cache_put(cache_key, resp)
    return resp
