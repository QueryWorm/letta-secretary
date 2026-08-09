import base64
import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_voices(client):
    r = client.get("/voices")
    assert r.status_code == 200
    assert "ru-RU-SvetlanaNeural" in r.json()["voices"]


def test_synthesize_basic(client):
    r = client.post("/synthesize", json={"text": "Привет, мир."})
    assert r.status_code == 200
    body = r.json()
    assert "audio_base64" in body
    assert body["filename"] == "response.ogg"
    assert body["duration_sec"] > 0
    assert body["synthesis_ms"] > 0
    assert body["truncated"] is False
    audio = base64.b64decode(body["audio_base64"])
    assert len(audio) > 100


def test_synthesize_with_explicit_voice(client):
    r = client.post("/synthesize", json={"text": "Тест", "voice": "ru-RU-DmitryNeural"})
    assert r.status_code == 200


def test_synthesize_truncation(client):
    long_text = "а" * 6000
    r = client.post("/synthesize", json={"text": long_text})
    assert r.status_code == 200
    assert r.json()["truncated"] is True
    assert r.json()["text_length"] == 6000


def test_synthesize_empty_text_rejected(client):
    r = client.post("/synthesize", json={"text": ""})
    assert r.status_code in (400, 422)


def test_synthesize_cache_hit(client):
    payload = {"text": "Кеш тест.", "voice": "ru-RU-SvetlanaNeural"}
    r1 = client.post("/synthesize", json=payload)
    r2 = client.post("/synthesize", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    # Same audio (cache hit)
    assert r1.json()["audio_base64"] == r2.json()["audio_base64"]
    # Cached call still returns same synthesis_ms value (cached)
    assert r1.json()["synthesis_ms"] == r2.json()["synthesis_ms"]
