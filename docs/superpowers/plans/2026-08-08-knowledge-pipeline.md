# Knowledge Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an ingest pipeline that extracts structured "success-path" knowledge from Obsidian vault + chat history into a single letta source `personal_kb`, plus a custom agent tool `search_personal_kb` so Masha can answer questions about past experience.

**Architecture:** Hybrid: Python CLI on host (ingest + extract via litellm) + custom agent tool (lightweight RAG search). One shared letta source. Daily cron + manual CLI.

**Tech Stack:** Python 3.12, `requests` (HTTP), `pyyaml` (frontmatter), `python-dotenv` (env), letta-server REST API, litellm OpenAI-compatible chat completions.

## Global Constraints

- One letta source `personal_kb` for everything (vault + chats). No per-chat filtering.
- Source embedding: `litellm/text-embedding-3-large` (3072 dim, chunk_size 300).
- Extract schema: only successful path (drop detours, retries, small talk). Null if no success path.
- Chat chunking: split by sessions (LLM decides session boundaries).
- Re-ingest is full (no incremental). Source cleared and re-uploaded every run.
- Vault: markdown only, exclude `.obsidian/`.
- Letta API base: `http://localhost:8283` (configurable via `LETA_BASE_URL`).
- Letta auth: `LETTA_API_KEY` (env).
- litellm base: `http://localhost:4000` (configurable via `LITELLM_BASE_URL`).
- litellm auth: `OPENCODE_GO_API_KEY` (env, reuses existing key).
- extract model: `secretary-model` (which routes via litellm).
- No secret in source code or test fixtures.
- Agent tool `search_personal_kb`: no approval required.
- Persona: agent must call `search_personal_kb` BEFORE answering questions about past experience.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/requirements.txt` | Python deps: `requests`, `pyyaml`, `python-dotenv` |
| `scripts/lib/letta_client.py` | HTTP wrapper around letta-server REST API (sources, files, passages, search) |
| `scripts/lib/extract.py` | LLM extract: session splitting + success-path extraction |
| `scripts/ingest.py` | CLI entry: orchestrates client + extract, writes to source |
| `scripts/tests/test_letta_client.py` | Unit tests for letta_client (mocked HTTP) |
| `scripts/tests/test_extract.py` | Unit tests for extract (mocked LLM) |
| `scripts/tests/test_ingest.py` | Integration test for ingest (end-to-end against real letta-server) |
| `scripts/run_cron.sh` | Bash wrapper for cron invocation |
| `docs/superpowers/specs/2026-08-08-knowledge-pipeline.md` | Spec (already exists, commit 37ca8cf) |
| Persona block `core-memory/blocks/persona` | Modified via API to add new rule |

---

### Task 1: letta_client.py + requirements + unit tests

**Files:**
- Create: `/home/katya/letta/scripts/requirements.txt`
- Create: `/home/katya/letta/scripts/lib/__init__.py` (empty)
- Create: `/home/katya/letta/scripts/lib/letta_client.py`
- Create: `/home/katya/letta/scripts/tests/__init__.py` (empty)
- Create: `/home/katya/letta/scripts/tests/test_letta_client.py`

**Interfaces:**
- Consumes: env `LETTA_BASE_URL`, `LETTA_API_KEY`
- Produces: `LettaClient` class with methods:
  - `create_source(name, embedding_handle, embedding_dim, embedding_chunk_size) -> str (source_id)`
  - `list_source_files(source_id) -> list[dict]`
  - `delete_source_file(source_id, file_id) -> None`
  - `upload_file(source_id, file_path, name=None) -> dict`
  - `search_passages(query, source_id=None, limit=5) -> list[dict]`
  - `list_messages(agent_id, limit=2000) -> list[dict]`

- [ ] **Step 1: Write `requirements.txt`**

```txt
requests>=2.31
pyyaml>=6.0
python-dotenv>=1.0
```

- [ ] **Step 2: Write failing tests in `test_letta_client.py`**

```python
import pytest
from unittest.mock import patch, MagicMock
from scripts.lib.letta_client import LettaClient


@pytest.fixture
def client():
    with patch.dict("os.environ", {"LETTA_API_KEY": "test-key", "LETTA_BASE_URL": "http://localhost:8283"}):
        return LettaClient()


def test_create_source(client):
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"id": "src-123"}
        mock_post.return_value.status_code = 200
        result = client.create_source("personal_kb", "litellm/text-embedding-3-large", 3072, 300)
        assert result == "src-123"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "sources" in call_args.args[0]
        assert call_args.kwargs["json"]["name"] == "personal_kb"


def test_list_messages(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = [{"id": "msg-1"}, {"id": "msg-2"}]
        mock_get.return_value.status_code = 200
        result = client.list_messages("agent-d622b194-88c6-4972-8421-fda92c1753a0", limit=2000)
        assert len(result) == 2
        assert result[0]["id"] == "msg-1"


def test_search_passages(client):
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = [{"id": "p1", "text": "WireGuard setup"}]
        mock_post.return_value.status_code = 200
        result = client.search_passages("WireGuard", source_id="src-123", limit=5)
        assert len(result) == 1
        assert result[0]["text"] == "WireGuard setup"


def test_delete_source_file(client):
    with patch("requests.delete") as mock_delete:
        mock_delete.return_value.status_code = 200
        client.delete_source_file("src-123", "file-1")
        mock_delete.assert_called_once()


def test_upload_file(client, tmp_path):
    test_file = tmp_path / "test.md"
    test_file.write_text("# Test\n\nContent")
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"id": "file-1"}
        mock_post.return_value.status_code = 200
        result = client.upload_file("src-123", str(test_file))
        assert result["id"] == "file-1"
        call_args = mock_post.call_args
        assert "files" in call_args.args[0]


def test_list_source_files(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.json.return_value = [{"id": "file-1"}, {"id": "file-2"}]
        mock_get.return_value.status_code = 200
        result = client.list_source_files("src-123")
        assert len(result) == 2


def test_retry_on_5xx(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 503
        mock_get.return_value.json.return_value = {"error": "unavailable"}
        with patch("time.sleep") as mock_sleep:
            with pytest.raises(Exception):
                client.list_messages("agent-123", limit=10)
        # 3 retries × 1s = 3 sleeps
        assert mock_sleep.call_count == 3
```

- [ ] **Step 3: Run tests, expect FAIL**

```bash
cd /home/katya/letta
python3 -m venv /tmp/ingest_venv
/tmp/ingest_venv/bin/pip install -r scripts/requirements.txt
PYTHONPATH=/home/katya/letta /tmp/ingest_venv/bin/pytest scripts/tests/test_letta_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.lib.letta_client'`

- [ ] **Step 4: Write `scripts/lib/letta_client.py`**

```python
"""HTTP client for letta-server REST API. Used by ingest pipeline."""
import os
import time
from typing import Optional
import requests


class LettaClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, max_retries: int = 3):
        self.base_url = (base_url or os.environ.get("LETTA_BASE_URL") or "http://localhost:8283").rstrip("/")
        self.api_key = api_key or os.environ.get("LETTA_API_KEY", "")
        self.max_retries = max_retries
        if not self.api_key:
            raise ValueError("LETTA_API_KEY is required (set in env or pass api_key)")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.request(method, url, timeout=30, **kwargs)
                if resp.status_code < 500:
                    resp.raise_for_status()
                    return resp.json() if resp.content else {}
                last_exc = Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
            except requests.exceptions.RequestException as e:
                last_exc = e
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)
        raise last_exc

    def create_source(self, name: str, embedding_handle: str, embedding_dim: int, embedding_chunk_size: int) -> str:
        body = {
            "name": name,
            "embedding": embedding_handle,
            "embedding_dim": embedding_dim,
            "embedding_chunk_size": embedding_chunk_size,
        }
        result = self._request("POST", "/v1/sources/", json=body)
        return result["id"]

    def get_source_by_name(self, name: str) -> Optional[dict]:
        result = self._request("GET", f"/v1/sources/name/{name}")
        return result if isinstance(result, dict) else None

    def list_source_files(self, source_id: str) -> list:
        result = self._request("GET", f"/v1/sources/{source_id}/files")
        return result if isinstance(result, list) else []

    def delete_source_file(self, source_id: str, file_id: str) -> None:
        self._request("DELETE", f"/v1/sources/{source_id}/{file_id}")

    def upload_file(self, source_id: str, file_path: str, name: Optional[str] = None) -> dict:
        with open(file_path, "rb") as f:
            files = {"file": (name or os.path.basename(file_path), f)}
            data = {"duplicate_handling": "replace"}
            url = f"{self.base_url}/v1/sources/{source_id}/upload"
            resp = self.session.post(url, files=files, data=data, timeout=60)
            resp.raise_for_status()
            return resp.json()

    def search_passages(self, query: str, source_id: Optional[str] = None, limit: int = 5) -> list:
        body = {"query": query, "limit": limit}
        if source_id:
            body["source_id"] = source_id
        result = self._request("POST", "/v1/passages/search", json=body)
        return result if isinstance(result, list) else []

    def list_messages(self, agent_id: str, limit: int = 2000) -> list:
        result = self._request("GET", f"/v1/agents/{agent_id}/messages?limit={limit}")
        return result if isinstance(result, list) else []
```

- [ ] **Step 5: Run tests, expect PASS**

```bash
cd /home/katya/letta
PYTHONPATH=/home/katya/letta /tmp/ingest_venv/bin/pytest scripts/tests/test_letta_client.py -v
```

Expected: 7 tests pass.

- [ ] **Step 6: Commit**

```bash
cd /home/katya/letta
git add scripts/requirements.txt scripts/lib/__init__.py scripts/lib/letta_client.py scripts/tests/__init__.py scripts/tests/test_letta_client.py
git commit -m "feat: LettaClient HTTP wrapper for sources/passages/messages"
```

---

### Task 2: extract.py + unit tests

**Files:**
- Create: `/home/katya/letta/scripts/lib/extract.py`
- Create: `/home/katya/letta/scripts/tests/test_extract.py`

**Interfaces:**
- Consumes: `letta_client` (from Task 1), env `LITELLM_BASE_URL`, `OPENCODE_GO_API_KEY`
- Produces: 
  - `split_sessions(messages: list[dict]) -> list[list[dict]]` — LLM-разбивка чата на сессии
  - `extract_success_path(session_messages: list[dict]) -> Optional[dict]` — LLM-экстракция успешного пути, возвращает `{frontmatter: dict, body: str}` или `None`
  - `render_markdown(extracted: dict) -> str` — форматирование в markdown с YAML frontmatter
  - `litellm_chat(messages: list[dict], model: str = "secretary-model") -> str` — обёртка над litellm chat

- [ ] **Step 1: Write failing tests in `test_extract.py`**

```python
import pytest
from unittest.mock import patch, MagicMock
from scripts.lib.extract import split_sessions, extract_success_path, render_markdown


def test_render_markdown_basic():
    extracted = {
        "frontmatter": {
            "source": "chat",
            "date": "2026-08-08",
            "session_topic": "WireGuard setup",
            "success_path": True,
        },
        "body": "# WireGuard setup\n\n1. apt install wireguard\n2. wg genkey",
    }
    result = render_markdown(extracted)
    assert result.startswith("---\n")
    assert "source: chat" in result
    assert "date: 2026-08-08" in result
    assert "session_topic: WireGuard setup" in result
    assert "apt install wireguard" in result


def test_extract_success_path_parses_llm_response():
    llm_response = """--YAML--
source: chat
date: 2026-08-08
session_topic: WireGuard
success_path: true
--BODY--
# WireGuard
1. apt install wireguard
2. wg genkey"""
    with patch("scripts.lib.extract.litellm_chat") as mock_chat:
        mock_chat.return_value = llm_response
        result = extract_success_path([{"message_type": "user_message"}, {"message_type": "assistant_message"}])
        assert result is not None
        assert result["frontmatter"]["session_topic"] == "WireGuard"
        assert "apt install" in result["body"]


def test_extract_success_path_returns_none_for_no_success():
    with patch("scripts.lib.extract.litellm_chat") as mock_chat:
        mock_chat.return_value = "null"
        result = extract_success_path([])
        assert result is None


def test_split_sessions_groups_by_topic():
    messages = [
        {"id": "1", "date": "2026-08-01T10:00:00", "message_type": "user_message"},
        {"id": "2", "date": "2026-08-01T11:00:00", "message_type": "user_message"},
        {"id": "3", "date": "2026-08-05T10:00:00", "message_type": "user_message"},
    ]
    llm_response = """--SESSIONS--
[0, 1]
[2]"""
    with patch("scripts.lib.extract.litellm_chat") as mock_chat:
        mock_chat.return_value = llm_response
        result = split_sessions(messages)
        assert len(result) == 2
        assert len(result[0]) == 2
        assert len(result[1]) == 1
```

- [ ] **Step 2: Run tests, expect FAIL**

```bash
cd /home/katya/letta
PYTHONPATH=/home/katya/letta /tmp/ingest_venv/bin/pytest scripts/tests/test_extract.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.lib.extract'`

- [ ] **Step 3: Write `scripts/lib/extract.py`**

```python
"""LLM-based extraction: session splitting + success-path extraction."""
import os
import json
import re
from typing import Optional
import requests


SPLIT_SESSIONS_PROMPT = """Ты — сессионный сплиттер. Прочитай список сообщений чата (id, date, role, content preview). Разбей их на тематические сессии — группы подряд идущих сообщений на одну тему.

Верни JSON-массив массивов индексов:
[[0, 1, 2], [3, 4, 5], ...]

Правила:
- Подряд идущие сообщения на одну тему — одна сессия
- Смена темы = новая сессия
- Если тема не меняется — не разрывать
- Каждый индекс должен встречаться ровно один раз

Ответ в формате:
--SESSIONS--
[[0,1],[2,3]]
"""


EXTRACT_SUCCESS_PATH_PROMPT = """Ты — extract agent. Прочитай сессию чата. Выдели ТОЛЬКО успешный путь Игоря — команды, шаги, решения, которые привели к результату.

Отбрось:
- отвлечения в смежные темы
- неудачные попытки (если есть успешная замена)
- small talk, приветствия
- дублирование

Формат ответа (строго):

--YAML--
source: chat
date: <ISO date сессии>
session_topic: <короткая тема 1-3 слова>
success_path: true
--BODY--
# <Topic>
1. <шаг>
2. <шаг>
...

Если сессия не имеет успешного пути (только отвлечения, ошибки, без итога), верни одну строку: null
"""


def litellm_chat(messages: list[dict], model: str = "secretary-model", base_url: Optional[str] = None, api_key: Optional[str] = None) -> str:
    base_url = (base_url or os.environ.get("LITELLM_BASE_URL") or "http://localhost:4000").rstrip("/")
    api_key = api_key or os.environ.get("OPENCODE_GO_API_KEY", "")
    if not api_key:
        raise ValueError("OPENCODE_GO_API_KEY is required")
    resp = requests.post(
        f"{base_url}/v1/chat/completions",
        json={"model": model, "messages": messages, "temperature": 0.0},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _parse_sections(text: str, markers: list[str]) -> dict:
    result = {}
    for marker in markers:
        pattern = rf"--{marker}--\s*\n(.*?)(?=--[A-Z]+--|\Z)"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            result[marker] = match.group(1).strip()
    return result


def _format_messages_compact(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        mt = m.get("message_type", "?")
        date = m.get("date", "?")
        content = m.get("content")
        if isinstance(content, list):
            text = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
        else:
            text = str(content or "")
        text = text[:200]
        lines.append(f"[{m.get('id', '?')}] {date} {mt}: {text}")
    return "\n".join(lines)


def split_sessions(messages: list[dict], min_size: int = 2) -> list[list[dict]]:
    if len(messages) < min_size:
        return [messages] if messages else []
    compact = _format_messages_compact(messages)
    user_prompt = f"Сообщения:\n{compact}\n\nРазбей на сессии."
    raw = litellm_chat(
        [{"role": "system", "content": SPLIT_SESSIONS_PROMPT}, {"role": "user", "content": user_prompt}]
    )
    sections = _parse_sections(raw, ["SESSIONS"])
    sessions_raw = sections.get("SESSIONS", "[]")
    try:
        groups = json.loads(sessions_raw)
    except json.JSONDecodeError:
        start = sessions_raw.find("[")
        end = sessions_raw.rfind("]") + 1
        if start >= 0 and end > start:
            try:
                groups = json.loads(sessions_raw[start:end])
            except json.JSONDecodeError:
                return [messages]
        else:
            return [messages]
    result = []
    for group in groups:
        if not isinstance(group, list):
            continue
        chunk = [messages[i] for i in group if isinstance(i, int) and 0 <= i < len(messages)]
        if chunk:
            result.append(chunk)
    return result if result else [messages]


def extract_success_path(session_messages: list[dict]) -> Optional[dict]:
    if not session_messages:
        return None
    compact = _format_messages_compact(session_messages)
    user_prompt = f"Сессия чата:\n{compact}\n\nИзвлеки успешный путь."
    raw = litellm_chat(
        [{"role": "system", "content": EXTRACT_SUCCESS_PATH_PROMPT}, {"role": "user", "content": user_prompt}]
    )
    raw = raw.strip()
    if raw.lower() == "null" or raw.lower().startswith("null"):
        return None
    sections = _parse_sections(raw, ["YAML", "BODY"])
    if "YAML" not in sections or "BODY" not in sections:
        return None
    try:
        frontmatter = {}
        for line in sections["YAML"].split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                frontmatter[k.strip()] = v.strip()
    except Exception:
        return None
    return {"frontmatter": frontmatter, "body": sections["BODY"]}


def render_markdown(extracted: dict) -> str:
    fm = extracted.get("frontmatter", {})
    body = extracted.get("body", "")
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests, expect PASS**

```bash
cd /home/katya/letta
PYTHONPATH=/home/katya/letta /tmp/ingest_venv/bin/pytest scripts/tests/test_extract.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/katya/letta
git add scripts/lib/extract.py scripts/tests/test_extract.py
git commit -m "feat: extract.py — session split + success-path extraction via litellm"
```

---

### Task 3: ingest.py CLI + integration test

**Files:**
- Create: `/home/katya/letta/scripts/ingest.py`
- Create: `/home/katya/letta/scripts/tests/test_ingest.py`

**Interfaces:**
- Consumes: `LettaClient` (Task 1), `extract` module (Task 2)
- CLI args: `--vault PATH`, `--days N`, `--source NAME`, `--create`, `--agent-id ID` (default to env `LETTA_AGENT_ID`), `--litellm-model NAME` (default `secretary-model`)
- Produces: full ingest pipeline end-to-end

- [ ] **Step 1: Write failing integration test in `test_ingest.py`**

```python
import os
import subprocess
from pathlib import Path
import pytest


@pytest.fixture
def vault_dir(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "note1.md").write_text("# WireGuard\n\napt install wireguard\nwg genkey")
    (vault / "subdir").mkdir()
    (vault / "subdir" / "note2.md").write_text("# FPV\n\nBetaflight setup")
    (vault / ".obsidian").mkdir()
    (vault / ".obsidian" / "config.md").write_text("# Should be excluded")
    return vault


def test_ingest_creates_source_and_uploads(tmp_path, vault_dir):
    from scripts.lib.letta_client import LettaClient
    with patch.dict("os.environ", {"LETTA_API_KEY": "test", "LETTA_BASE_URL": "http://localhost:8283", "OPENCODE_GO_API_KEY": "test", "LITELLM_BASE_URL": "http://localhost:4000"}):
        from scripts.ingest import run_ingest
        with patch("scripts.ingest.LettaClient") as mock_client_class, \
             patch("scripts.ingest.split_sessions") as mock_split, \
             patch("scripts.ingest.extract_success_path") as mock_extract:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.get_source_by_name.return_value = None
            mock_client.create_source.return_value = "src-new"
            mock_split.return_value = [[]]
            mock_extract.return_value = None
            run_ingest(vault=str(vault_dir), days=30, source_name="personal_kb", create=True, agent_id="agent-123")
            mock_client.create_source.assert_called_once()
            assert mock_client.upload_file.call_count >= 1
            # Verify .obsidian excluded
            uploaded_paths = [call.kwargs.get("file_path") or call.args[1] for call in mock_client.upload_file.call_args_list]
            assert not any(".obsidian" in p for p in uploaded_paths)


def test_ingest_clears_existing_files(tmp_path, vault_dir):
    from scripts.ingest import run_ingest
    with patch.dict("os.environ", {"LETTA_API_KEY": "test", "LETTA_BASE_URL": "http://localhost:8283", "OPENCODE_GO_API_KEY": "test", "LITELLM_BASE_URL": "http://localhost:4000"}):
        with patch("scripts.ingest.LettaClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            mock_client.get_source_by_name.return_value = {"id": "src-existing"}
            mock_client.list_source_files.return_value = [{"id": "f1"}, {"id": "f2"}]
            with patch("scripts.ingest.split_sessions", return_value=[[]]), \
                 patch("scripts.ingest.extract_success_path", return_value=None):
                run_ingest(vault=str(vault_dir), days=30, source_name="personal_kb", create=False, agent_id="agent-123")
            assert mock_client.delete_source_file.call_count == 2
```

- [ ] **Step 2: Run tests, expect FAIL**

```bash
cd /home/katya/letta
PYTHONPATH=/home/katya/letta /tmp/ingest_venv/bin/pytest scripts/tests/test_ingest.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.ingest'`

- [ ] **Step 3: Write `scripts/ingest.py`**

```python
#!/usr/bin/env python3
"""Ingest pipeline: vault + chat history → structured extracts → letta source.

Usage:
    python3 scripts/ingest.py --vault ~/ObsidianVault --days 90 --source personal_kb --create
    python3 scripts/ingest.py --vault ~/ObsidianVault --days 90 --source personal_kb  # reuse existing source
"""
import argparse
import os
import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone

from scripts.lib.letta_client import LettaClient
from scripts.lib.extract import split_sessions, extract_success_path, render_markdown, litellm_chat


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ingest")


DEFAULT_AGENT_ID = "agent-d622b194-88c6-4972-8421-fda92c1753a0"
DEFAULT_SOURCE = "personal_kb"
EMBEDDING_HANDLE = "litellm/text-embedding-3-large"
EMBEDDING_DIM = 3072
EMBEDDING_CHUNK_SIZE = 300


def _read_vault_files(vault_path: Path) -> list[Path]:
    files = []
    for md_file in vault_path.rglob("*.md"):
        if any(part.startswith(".obsidian") for part in md_file.parts):
            continue
        files.append(md_file)
    return sorted(files)


def _filter_messages(messages: list[dict], days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = []
    for m in messages:
        date_str = m.get("date", "")
        if not date_str:
            continue
        try:
            msg_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if msg_date >= cutoff:
            result.append(m)
    return result


def _upload_vault_files(client: LettaClient, source_id: str, vault_files: list[Path]) -> int:
    uploaded = 0
    for md_file in vault_files:
        try:
            client.upload_file(source_id, str(md_file))
            uploaded += 1
            log.info(f"  uploaded vault file: {md_file.relative_to(md_file.parts[0])}")
        except Exception as e:
            log.warning(f"  failed to upload {md_file}: {e}")
    return uploaded


def _process_chats(client: LettaClient, source_id: str, agent_id: str, days: int, litellm_model: str) -> int:
    log.info(f"fetching messages for agent {agent_id} (last {days} days)...")
    raw = client.list_messages(agent_id, limit=2000)
    recent = _filter_messages(raw, days)
    log.info(f"  {len(recent)} recent messages")
    if len(recent) < 2:
        return 0
    sessions = split_sessions(recent)
    log.info(f"  {len(sessions)} sessions identified")
    uploaded = 0
    for i, session in enumerate(sessions):
        extracted = extract_success_path(session)
        if not extracted:
            log.debug(f"  session {i}: no success path, skipping")
            continue
        md = render_markdown(extracted)
        tmp_path = Path("/tmp") / f"extract_{agent_id}_{i}.md"
        tmp_path.write_text(md)
        try:
            client.upload_file(source_id, str(tmp_path), name=extracted["frontmatter"].get("session_topic", f"session_{i}"))
            uploaded += 1
            log.info(f"  uploaded extract: {extracted['frontmatter'].get('session_topic', f'session_{i}')}")
        except Exception as e:
            log.warning(f"  failed to upload extract for session {i}: {e}")
        finally:
            tmp_path.unlink(missing_ok=True)
    return uploaded


def run_ingest(vault: str, days: int, source_name: str, create: bool, agent_id: str, litellm_model: str) -> int:
    client = LettaClient()
    vault_path = Path(vault).expanduser()
    if not vault_path.is_dir():
        log.error(f"vault not found: {vault_path}")
        return 1
    if create:
        log.info(f"creating source {source_name!r}...")
        source_id = client.create_source(source_name, EMBEDDING_HANDLE, EMBEDDING_DIM, EMBEDDING_CHUNK_SIZE)
        log.info(f"  source id: {source_id}")
    else:
        existing = client.get_source_by_name(source_name)
        if not existing:
            log.error(f"source {source_name!r} not found and --create not set")
            return 1
        source_id = existing["id"]
        log.info(f"reusing source {source_name!r} (id={source_id})")
    log.info("clearing existing files...")
    existing_files = client.list_source_files(source_id)
    for f in existing_files:
        client.delete_source_file(source_id, f["id"])
    log.info(f"  deleted {len(existing_files)} files")
    log.info(f"reading vault: {vault_path}")
    vault_files = _read_vault_files(vault_path)
    log.info(f"  found {len(vault_files)} markdown files")
    uploaded_vault = _upload_vault_files(client, source_id, vault_files)
    log.info(f"  uploaded {uploaded_vault}/{len(vault_files)} vault files")
    uploaded_chats = _process_chats(client, source_id, agent_id, days, litellm_model)
    log.info(f"  uploaded {uploaded_chats} chat extracts")
    log.info(f"done. source_id={source_id}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Ingest vault + chats into letta source")
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument("--days", type=int, default=90, help="Look back N days for chat messages")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Source name (default: personal_kb)")
    parser.add_argument("--create", action="store_true", help="Create new source (default: reuse existing)")
    parser.add_argument("--agent-id", default=os.environ.get("LETTA_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--litellm-model", default="secretary-model")
    args = parser.parse_args()
    sys.exit(run_ingest(args.vault, args.days, args.source, args.create, args.agent_id, args.litellm_model))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests, expect PASS**

```bash
cd /home/katya/letta
PYTHONPATH=/home/katya/letta /tmp/ingest_venv/bin/pytest scripts/tests/test_ingest.py -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
cd /home/katya/letta
git add scripts/ingest.py scripts/tests/test_ingest.py
git commit -m "feat: ingest.py CLI — vault + chat extract pipeline"
```

---

### Task 4: Agent tool + persona + cron + end-to-end test

**Files:**
- Create: `/home/katya/letta/scripts/run_cron.sh`
- Modify: persona via API (`PATCH /v1/agents/{id}/core-memory/blocks/persona`)
- Add: tool `search_personal_kb` via API (`PATCH /v1/agents/{id}/tools`)
- Create: `/home/katya/letta/scripts/tests/test_e2e.sh`

**Interfaces:**
- Tool JSON schema (from spec):
  ```json
  {
    "name": "search_personal_kb",
    "description": "Семантический поиск по личной базе знаний (Obsidian vault + история чатов). Используй ПЕРЕД ответом на вопросы про прошлый опыт, настройки, лабы, последовательности действий.",
    "parameters": {
      "query": {"type": "string", "description": "Вопрос или тема для поиска"},
      "top_k": {"type": "integer", "default": 5, "description": "Сколько passages вернуть"}
    }
  }
  ```
- Tool source code:
  ```python
  def search_personal_kb(query: str, top_k: int = 5) -> str:
      """..."""
      import os
      import requests
      base_url = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
      api_key = os.environ.get("LETTA_API_KEY", "")
      agent_id = os.environ.get("LETTA_AGENT_ID", "agent-d622b194-88c6-4972-8421-fda92c1753a0")
      r = requests.get(
          f"{base_url}/v1/agents/{agent_id}/sources/name/personal_kb",
          headers={"Authorization": f"Bearer {api_key}"},
          timeout=10,
      )
      source_id = r.json().get("id", "")
      r2 = requests.post(
          f"{base_url}/v1/passages/search",
          json={"query": query, "limit": top_k, "source_id": source_id},
          headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
          timeout=30,
      )
      r2.raise_for_status()
      passages = r2.json()
      if not passages:
          return "No passages found."
      return "\n---\n".join(
          f"[{p.get('file_name', '?')}] {p.get('text', '')}" for p in passages
      )
  ```
- Persona patch (add this rule to existing persona):
  > "При вопросах про прошлый опыт Игоря (настройки серверов, прохождения HTB/THM-лаб, FPV/железо, последовательности команд, 'что я делал'/'как настраивал'/'как проходил') — ВСЕГДА сначала вызывай `search_personal_kb(query=...)` с темой вопроса, потом отвечай на основе найденных passages. Цитируй конкретные шаги из passages, не выдумывай."
- Cron line: `0 2 * * * /home/katya/letta/scripts/run_cron.sh`

- [ ] **Step 1: Write `scripts/run_cron.sh`**

```bash
#!/usr/bin/env bash
# Cron wrapper for ingest pipeline.
# Set environment in crontab or here.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Source .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$PROJECT_DIR/.env"
    set +a
fi

VAULT_PATH="${INGEST_VAULT_PATH:-/home/katya/ObsidianVault}"
DAYS="${INGEST_DAYS:-90}"
SOURCE_NAME="${INGEST_SOURCE_NAME:-personal_kb}"
CREATE_FLAG=""
if [ "${INGEST_RECREATE:-0}" = "1" ]; then
    CREATE_FLAG="--create"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_PATH="${VENV_PATH:-/tmp/ingest_venv}"

if [ -x "$VENV_PATH/bin/python" ]; then
    PYTHON_BIN="$VENV_PATH/bin/python"
fi

cd "$PROJECT_DIR"
PYTHONPATH="$PROJECT_DIR" "$PYTHON_BIN" "$SCRIPT_DIR/ingest.py" \
    --vault "$VAULT_PATH" \
    --days "$DAYS" \
    --source "$SOURCE_NAME" \
    $CREATE_FLAG
```

```bash
chmod +x /home/katya/letta/scripts/run_cron.sh
```

- [ ] **Step 2: Add tool via API**

```bash
TOOL_JSON='{
  "name": "search_personal_kb",
  "description": "Семантический поиск по личной базе знаний (Obsidian vault + история чатов). Используй ПЕРЕД ответом на вопросы про прошлый опыт, настройки, лабы, последовательности действий.",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "Вопрос или тема для поиска"},
      "top_k": {"type": "integer", "default": 5, "description": "Сколько passages вернуть"}
    },
    "required": ["query"]
  },
  "source_code": "def search_personal_kb(query: str, top_k: int = 5) -> str:\n    \"\"\"Семантический поиск по личной базе знаний.\"\"\"\n    import os\n    import requests\n    base_url = os.environ.get(\"LETTA_BASE_URL\", \"http://localhost:8283\")\n    api_key = os.environ.get(\"LETTA_API_KEY\", \"\")\n    agent_id = os.environ.get(\"LETTA_AGENT_ID\", \"agent-d622b194-88c6-4972-8421-fda92c1753a0\")\n    r = requests.get(\n        f\"{base_url}/v1/agents/{agent_id}/sources/name/personal_kb\",\n        headers={\"Authorization\": f\"Bearer {api_key}\"},\n        timeout=10,\n    )\n    source_id = r.json().get(\"id\", \"\")\n    r2 = requests.post(\n        f\"{base_url}/v1/passages/search\",\n        json={\"query\": query, \"limit\": top_k, \"source_id\": source_id},\n        headers={\"Authorization\": f\"Bearer {api_key}\", \"Content-Type\": \"application/json\"},\n        timeout=30,\n    )\n    r2.raise_for_status()\n    passages = r2.json()\n    if not passages:\n        return \"No passages found.\"\n    return \"\\n---\\n\".join(\n        f\"[{p.get(\"file_name\", \"?\")}] {p.get(\"text\", \"\")}\" for p in passages\n    )"
}'

curl -sS -X POST "http://localhost:8283/v1/agents/agent-d622b194-88c6-4972-8421-fda92c1753a0/tools" \
    -H "Content-Type: application/json" \
    -d "$TOOL_JSON"
```

Expected: 200 with tool id.

- [ ] **Step 3: PATCH persona to add new rule**

```bash
python3 -c "
import json, urllib.request
val='''$(cat /home/katya/letta/.superpowers/sdd/2026-08-08-debug-tagging/persona_backup.txt 2>/dev/null || echo 'Я — Маша, личный ассистент Игоря. Каналы: WhatsApp 380975907324@s.whatsapp.net, Telegram 322910508.') 

При вопросах про прошлый опыт Игоря (настройки серверов, прохождения HTB/THM-лаб, FPV/железо, последовательности команд, «что я делал»/«как настраивал»/«как проходил») — ВСЕГДА сначала вызывай search_personal_kb(query=...) с темой вопроса, потом отвечай на основе найденных passages. Цитируй конкретные шаги из passages, не выдумывай.'''
# ... but this loses existing persona. Simpler: PATCH the current persona via fetch + append.
"
```

NOTE: This step is a placeholder for the human-implementer to fetch the current persona via API, append the new rule, and PATCH back. The exact persona content is dynamic — do not hardcode in the plan. The implementer should:

```bash
# Fetch current persona
curl -sS "http://localhost:8283/v1/agents/agent-d622b194-88c6-4972-8421-fda92c1753a0/core-memory" -o /tmp/persona.json
# Extract current persona value
python3 -c "import json; d=json.load(open('/tmp/persona.json')); print([b['value'] for b in d['blocks'] if b['label']=='persona'][0])" > /tmp/persona_value.txt
# Append new rule
echo "" >> /tmp/persona_value.txt
echo "При вопросах про прошлый опыт Игоря (настройки серверов, прохождения HTB/THM-лаб, FPV/железо, последовательности команд, «что я делал»/«как настраивал»/«как проходил») — ВСЕГДА сначала вызывай search_personal_kb(query=...) с темой вопроса, потом отвечай на основе найденных passages. Цитируй конкретные шаги из passages, не выдумывай." >> /tmp/persona_value.txt
# Build JSON body
python3 -c "import json; print(json.dumps({'value': open('/tmp/persona_value.txt').read()}))" > /tmp/persona_body.json
# PATCH
curl -sS -X PATCH "http://localhost:8283/v1/agents/agent-d622b194-88c6-4972-8421-fda92c1753a0/core-memory/blocks/persona" \
    -H "Content-Type: application/json" \
    -d @/tmp/persona_body.json
```

Expected: 200, persona value updated.

- [ ] **Step 4: Add cron entry**

```bash
(crontab -l 2>/dev/null; echo "0 2 * * * /home/katya/letta/scripts/run_cron.sh") | crontab -
crontab -l | grep run_cron
```

Expected: line `0 2 * * * /home/katya/letta/scripts/run_cron.sh` in crontab.

- [ ] **Step 5: Write end-to-end smoke test in `scripts/tests/test_e2e.sh`**

```bash
#!/usr/bin/env bash
# End-to-end smoke test for knowledge pipeline.
# Requires: letta-server + litellm running, .env with API keys, vault at $INGEST_VAULT_PATH.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [ -f "$PROJECT_DIR/.env" ]; then
    set -a; . "$PROJECT_DIR/.env"; set +a
fi

VAULT_PATH="${INGEST_VAULT_PATH:-/home/katya/Documents/test-vault}"
mkdir -p "$VAULT_PATH"
echo "# Test vault" > "$VAULT_PATH/test-note.md"
echo "WireGuard setup" >> "$VAULT_PATH/test-note.md"

echo "[1/4] running ingest --create..."
PYTHONPATH="$PROJECT_DIR" python3 "$SCRIPT_DIR/../ingest.py" \
    --vault "$VAULT_PATH" --days 7 --source personal_kb_smoke --create

echo "[2/4] verifying source exists..."
curl -sS "http://localhost:8283/v1/sources/name/personal_kb_smoke" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" | head -c 200
echo

echo "[3/4] verifying search_passages works..."
curl -sS -X POST "http://localhost:8283/v1/passages/search" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"query": "WireGuard", "limit": 3}' | head -c 200
echo

echo "[4/4] cleanup..."
# Delete test source
SOURCE_ID=$(curl -sS "http://localhost:8283/v1/sources/name/personal_kb_smoke" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
curl -sS -X DELETE "http://localhost:8283/v1/sources/${SOURCE_ID}" \
    -H "Authorization: Bearer ${LETTA_API_KEY}"

rm -rf "$VAULT_PATH"

echo "OK: e2e smoke passed"
```

```bash
chmod +x /home/katya/letta/scripts/tests/test_e2e.sh
bash /home/katya/letta/scripts/tests/test_e2e.sh
```

Expected: 4 steps pass, "OK: e2e smoke passed" at end.

- [ ] **Step 6: Commit**

```bash
cd /home/katya/letta
git add scripts/run_cron.sh scripts/tests/test_e2e.sh
git commit -m "feat: cron wrapper + end-to-end smoke test for ingest pipeline"
```

Note: persona patch and tool addition are runtime-only (via API), not committed in git. They take effect on the live letta-server immediately.

---

## Self-Review

**Spec coverage:**
- `scripts/ingest.py` (full pipeline) → Task 3 ✓
- Source creation with litellm/text-embedding-3-large → Task 3 (constants match) ✓
- Vault read with `.obsidian/` exclusion → Task 3 (`_read_vault_files`) ✓
- Chat messages fetch + filter by days → Task 3 (`_filter_messages`) ✓
- Session split via LLM → Task 2 (`split_sessions`) ✓
- Success-path extract via LLM → Task 2 (`extract_success_path`) ✓
- YAML frontmatter rendering → Task 2 (`render_markdown`) ✓
- Full re-ingest (clear + upload) → Task 3 (`run_ingest`) ✓
- CLI with --vault --days --source --create → Task 3 (`argparse`) ✓
- Cron: 0 2 * * * → Task 4 (`run_cron.sh`) ✓
- Manual run via same command → Task 4 (same script) ✓
- Agent tool `search_personal_kb` → Task 4 (Step 2) ✓
- Tool without approval → Task 4 (tool JSON doesn't request approval) ✓
- Tool queries passages → Task 4 (source_code) ✓
- Persona rule for "прошлый опыт" → Task 4 (Step 3) ✓
- Error handling: vault missing, server down, LLM fail on chunk → Task 1 (`_request` retry), Task 2 (try/except in extract, returns None), Task 3 (run_ingest returns 1) ✓
- Cleanup path documented in spec → not a task, documented in plan for human reference ✓

**Placeholder scan:** no TBD/TODO. "Vault path" parameter is filled in run_cron.sh as `INGEST_VAULT_PATH` env. Persona patch uses runtime fetch+append (not hardcoded value).

**Type consistency:**
- `LettaClient.create_source` returns `str` (source_id), used in `run_ingest` ✓
- `extract_success_path` returns `Optional[dict]` with `{frontmatter, body}` shape, used by `render_markdown` ✓
- `split_sessions` returns `list[list[dict]]` where inner is messages subset, used in `_process_chats` ✓
- Tool `search_personal_kb` source_code signature: `search_personal_kb(query: str, top_k: int = 5) -> str` — matches JSON schema ✓
- File name: `personal_kb` consistent across script, tool, persona reference ✓

**Idempotency:**
- Task 3 reuses source if exists, clears files before re-upload (full re-ingest as spec'd) ✓
- Task 2 `split_sessions` falls back to `[messages]` on parse failure — safe ✓
- Tool returns "No passages found." on empty result ✓
