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


def _parse_groups(sessions_raw: str, n: int) -> Optional[list]:
    try:
        return json.loads(sessions_raw)
    except json.JSONDecodeError:
        pass
    start = sessions_raw.find("[")
    end = sessions_raw.rfind("]") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(sessions_raw[start:end])
        except json.JSONDecodeError:
            pass
    bracket_groups = re.findall(r"\[[^\[\]]*\]", sessions_raw)
    if len(bracket_groups) >= 2:
        try:
            return [json.loads(g) for g in bracket_groups]
        except json.JSONDecodeError:
            return None
    return None


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
    groups = _parse_groups(sessions_raw, len(messages))
    if groups is None:
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
