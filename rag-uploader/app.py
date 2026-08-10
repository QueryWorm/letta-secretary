"""RAG uploader: split-and-upload text into letta-server archive.

Single-page web form. POST /upload takes text, splits into chunks, sends
via POST /v1/archives/{archive_id}/passages/batch to letta-server.
"""
import os
import re
import time
from collections import deque
from typing import List, Optional

import httpx
from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel


LETTA_BASE_URL = os.environ.get("LETTA_BASE_URL", "http://letta-server:8283")
LETTA_API_KEY = os.environ.get("LETTA_API_KEY", "")
ARCHIVE_ID = os.environ.get("ARCHIVE_ID", "archive-68b3e817-5b14-4bf0-a524-0808b530eac2")
DEFAULT_CHUNK_SIZE = int(os.environ.get("DEFAULT_CHUNK_SIZE", "2000"))
HISTORY_MAX = 20

app = FastAPI(title="RAG Uploader", docs_url=None, redoc_url=None)
HISTORY: deque = deque(maxlen=HISTORY_MAX)


# --- chunking -------------------------------------------------------------

def split_into_chunks(text: str, chunk_size: int) -> List[str]:
    """Split text into chunks no larger than chunk_size.

    Strategy: split by paragraph (\n\n), accumulate, then split any
    oversized paragraph by sentence / line / char.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []
    current = ""

    for p in paragraphs:
        if len(p) > chunk_size:
            # flush current
            if current:
                chunks.append(current.strip())
                current = ""
            # split oversized paragraph
            chunks.extend(_split_large(p, chunk_size))
        elif len(current) + 2 + len(p) <= chunk_size:
            current = (current + "\n\n" + p).strip() if current else p
        else:
            if current:
                chunks.append(current.strip())
            current = p

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c]


def _split_large(text: str, chunk_size: int) -> List[str]:
    """Split one oversized block into <= chunk_size pieces."""
    # try sentences
    sentences = re.split(r"(?<=[.!?])\s+", text)
    out = []
    cur = ""
    for s in sentences:
        if len(s) > chunk_size:
            if cur:
                out.append(cur.strip())
                cur = ""
            out.extend(_split_by_lines(s, chunk_size))
        elif len(cur) + 1 + len(s) <= chunk_size:
            cur = (cur + " " + s).strip() if cur else s
        else:
            if cur:
                out.append(cur.strip())
            cur = s
    if cur:
        out.append(cur.strip())
    return [c for c in out if c]


def _split_by_lines(text: str, chunk_size: int) -> List[str]:
    out = []
    cur = ""
    for line in text.split("\n"):
        if len(line) > chunk_size:
            if cur:
                out.append(cur.strip())
                cur = ""
            # split by chars
            for i in range(0, len(line), chunk_size):
                out.append(line[i:i + chunk_size].strip())
        elif len(cur) + 1 + len(line) <= chunk_size:
            cur = (cur + "\n" + line).strip() if cur else line
        else:
            if cur:
                out.append(cur.strip())
            cur = line
    if cur:
        out.append(cur.strip())
    return [c for c in out if c]


# --- upload ---------------------------------------------------------------

class UploadSummary(BaseModel):
    timestamp: float
    chars_in: int
    chunks: int
    chunk_size: int
    tags: List[str]
    passage_ids: List[str]
    errors: List[str]


async def upload_to_letta(chunks: List[str], tags: List[str]) -> tuple[List[str], List[str]]:
    """POST batch to letta-server. Returns (passage_ids, errors)."""
    metadata = {"tags": tags} if tags else {}
    payload = {"passages": [{"text": c, "metadata": metadata} for c in chunks]}

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{LETTA_BASE_URL}/v1/archives/{ARCHIVE_ID}/passages/batch",
            json=payload,
            headers={"Authorization": f"Bearer {LETTA_API_KEY}"},
        )

    if r.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"letta-server {r.status_code}: {r.text[:300]}")

    # batch endpoint returns list of Passage objects
    body = r.json()
    if isinstance(body, list):
        ids = [p.get("id", "") for p in body]
        return ids, []
    return [], ["unexpected response shape"]


# --- routes ---------------------------------------------------------------

INDEX_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>RAG Uploader</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  h1 { font-size: 1.4rem; margin-bottom: 0.2rem; }
  .meta { color: #666; font-size: 0.9rem; margin-bottom: 1.5rem; }
  textarea { width: 100%; min-height: 320px; font-family: ui-monospace, monospace; font-size: 0.9rem; padding: 0.5rem; box-sizing: border-box; }
  .row { display: flex; gap: 1rem; margin: 1rem 0; align-items: center; }
  .row label { font-size: 0.9rem; color: #555; }
  input[type=text], input[type=number] { padding: 0.3rem 0.5rem; font-size: 0.95rem; }
  input[name=tags] { flex: 1; }
  input[name=chunk_size] { width: 80px; }
  button { padding: 0.5rem 1.2rem; background: #2c6e49; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }
  button:hover { background: #245a3c; }
  .result { margin-top: 1.5rem; padding: 1rem; border-radius: 4px; }
  .result.ok { background: #e6f4ea; border: 1px solid #2c6e49; }
  .result.err { background: #fce8e6; border: 1px solid #c5221f; }
  pre { background: #f5f5f5; padding: 0.5rem; border-radius: 4px; overflow-x: auto; font-size: 0.85rem; }
  table { border-collapse: collapse; width: 100%; margin-top: 1rem; font-size: 0.9rem; }
  th, td { border-bottom: 1px solid #ddd; padding: 0.4rem 0.6rem; text-align: left; }
  th { background: #f5f5f5; }
  code { background: #f5f5f5; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.85rem; }
</style>
</head>
<body>
<h1>RAG Uploader</h1>
<div class="meta">
  Archive: <code>__ARCHIVE__</code> · letta-server: <code>__LETTA__</code>
</div>

<form method="post" action="/upload">
  <textarea name="text" placeholder="Вставь текст сюда. Программа сама разрежет на чанки и зальёт." required></textarea>
  <div class="row">
    <label>tags (через запятую):</label>
    <input type="text" name="tags" placeholder="например: network, microtic, fpv">
    <label>chunk size:</label>
    <input type="number" name="chunk_size" value="__DEFAULT_CHUNK_SIZE__" min="500" max="8000">
    <button type="submit">Залить</button>
  </div>
</form>

<h2 style="font-size: 1.1rem; margin-top: 2rem;">Последние заливки</h2>
<table>
  <tr><th>время</th><th>chars</th><th>chunks</th><th>size</th><th>tags</th><th>ids</th></tr>
  __HISTORY__
</table>
</body>
</html>"""


def render_index() -> str:
    history_rows = []
    for h in reversed(list(HISTORY)):
        ts = time.strftime("%H:%M:%S", time.localtime(h.timestamp))
        ids_short = ", ".join(h.passage_ids[:3])
        if len(h.passage_ids) > 3:
            ids_short += f"… (+{len(h.passage_ids) - 3})"
        tags = ", ".join(h.tags) if h.tags else "—"
        history_rows.append(
            f"<tr><td>{ts}</td><td>{h.chars_in}</td><td>{h.chunks}</td>"
            f"<td>{h.chunk_size}</td><td>{tags}</td>"
            f"<td><code>{ids_short}</code></td></tr>"
        )
    return (
        INDEX_HTML
        .replace("__ARCHIVE__", ARCHIVE_ID)
        .replace("__LETTA__", LETTA_BASE_URL)
        .replace("__DEFAULT_CHUNK_SIZE__", str(DEFAULT_CHUNK_SIZE))
        .replace("__HISTORY__", "\n".join(history_rows) if history_rows else "<tr><td colspan=6 style='color:#999'>ещё ничего</td></tr>")
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return render_index()


@app.post("/upload")
async def upload(
    text: str = Form(""),
    tags: str = Form(""),
    chunk_size: int = Form(DEFAULT_CHUNK_SIZE),
    file: UploadFile = File(None),
):
    chunk_size = max(500, min(8000, chunk_size))
    tags_list = [t.strip() for t in tags.split(",") if t.strip()]

    if file is not None:
        raw = await file.read()
        text = raw.decode("utf-8", errors="replace")

    if not text.strip():
        raise HTTPException(status_code=400, detail="empty text (provide 'text' field or 'file' upload)")

    chunks = split_into_chunks(text, chunk_size)
    if not chunks:
        raise HTTPException(status_code=400, detail="text produced no chunks")

    ids, errors = await upload_to_letta(chunks, tags_list)

    summary = UploadSummary(
        timestamp=time.time(),
        chars_in=len(text),
        chunks=len(chunks),
        chunk_size=chunk_size,
        tags=tags_list,
        passage_ids=ids,
        errors=errors,
    )
    HISTORY.append(summary)

    return JSONResponse({
        "chunks": len(chunks),
        "chunk_size": chunk_size,
        "passage_ids": ids,
        "errors": errors,
        "chars_in": len(text),
    })


@app.get("/history")
async def history():
    return [h.model_dump() for h in HISTORY]


@app.get("/health")
async def health():
    return {"status": "ok", "archive": ARCHIVE_ID, "letta": LETTA_BASE_URL}
