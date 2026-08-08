# Knowledge Pipeline — Дизайн

**Дата:** 2026-08-08
**Статус:** утверждён
**Объём:** MVP — общий RAG-котёл по Obsidian vault + чатам + extract успешного пути

## Цель

Дать Маше возможность отвечать на вопросы про прошлый опыт Игоря
(настройки серверов, прохождения HTB-лаб, FPV-конфиги) на основе
**структурированных** извлечений из чатов и Obsidian-vault, а не сырого
лога диалогов.

## Зачем

Сейчас в чатах с Машей много ценного: пошаговые настройки серверов,
walkthrough'ы HTB-лаб, FPV-калибровки. Но это всё в виде длинных
диалогов с отклонениями в смежные темы и неудачными попытками. Найти
«успешный путь» в таком логе — трудно.

Решение: extract pipeline — LLM читает чат, выделяет только успешную
последовательность шагов, результат сохраняется в один общий letta-source.
RAG-поиск по этому source даёт быстрый и релевантный ответ.

## Архитектура

```
┌─ Obsidian vault (markdown)  ──┐
│                                │
│  letta-server /v1/messages     │──►  ingest.py (хост)  ──►  letta source
│  (чаты WhatsApp + Telegram)    │      ↓                     «personal_kb»
│                                │      LLM extract
│  (будущее: TG-каналы)         │      (litellm qwen)
└────────────────────────────────┘      ↓
                                        ▲
                                        │
                            search_personal_kb (тул агента)
                                        ↓
                                   Маша (агент Igor)
```

## Подход: Hybrid

- **Ingest + extract** — Python-скрипт на хосте. Тяжёлая обработка, не
  через тулы агента (агент не должен сам себя LLM-обрабатывать).
- **Search** — кастомный тул агента, который делает `POST /v1/passages/search`
  к letta-server. Лёгкий, быстрый, agent-friendly.
- **Cron** — внешний, раз в день в 2:00. Ручной запуск — той же командой.

## Компоненты

### 1. `scripts/ingest.py` (хост)

- Аргументы CLI: `--vault <path>`, `--days <N>`, `--source <name>`, `--create`
- Шаги:
  1. Если `--create`: создать source через `POST /v1/sources/` с embedding
     `litellm/text-embedding-3-large` (3072 dim, chunk_size 300)
  2. Очистить source: перечислить files через `GET /v1/sources/{id}/files`,
     удалить каждый через `DELETE /v1/sources/{id}/{file_id}`
  3. Прочитать vault: рекурсивно `*.md`, исключить `.obsidian/`, прикрепить
     frontmatter с датой и путём
  4. Прочитать чаты: `GET /v1/agents/{id}/messages?limit=2000`,
     фильтр по `message_type IN ('user_message', 'assistant_message')`,
     диапазон по `date >= now - days`
  5. **Extract pipeline** (для чатов):
     - LLM-разбивка чата на сессии по темам (`session_splitter.py`-style промпт)
     - Для каждой сессии — extract по schema: только успешный путь
     - На выходе — markdown с YAML-frontmatter:
       ```yaml
       ---
       source: chat
       date: 2026-08-08
       session_topic: WireGuard
       success_path: true
       ---
       # WireGuard setup
       1. apt install wireguard
       2. wg genkey | tee privatekey | wg pubkey > publickey
       3. ...
       ```
  6. Загрузить все результаты: `POST /v1/sources/{id}/upload` для каждого
     markdown-файла (multipart, `duplicate_handling=replace`)
- Логирование: stderr, прогресс
- Таймауты: 5 минут на extract через LLM, 3 retry на HTTP

### 2. Cron-задача

```
0 2 * * * /usr/bin/python3 /home/katya/letta/scripts/ingest.py --vault ~/ObsidianVault --days 90 --source personal_kb
```

(Путь к vault уточняется при имплементации — `Другой` из вопроса.)

### 3. Кастомный тул агента `search_personal_kb`

- JSON Schema:
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
- Backend: HTTP POST на `http://localhost:8283/v1/passages/search` с
  `{ "query": query, "limit": top_k, "source_id": "<personal_kb id>" }`
- Результат: список passages с `text` (чанк), `file_name`, `source_id`
- Без approval (как `describe_image`)

### 4. Persona дополнение

PATCH `core-memory/blocks/persona` — новое правило:

> «При вопросах про прошлый опыт Игоря (настройки серверов, прохождения
> HTB/THM-лаб, FPV/железо, последовательности команд, 'что я делал'/'как
> настраивал'/'как проходил') — ВСЕГДА сначала вызывай
> `search_personal_kb(query=...)` с темой вопроса, потом отвечай на основе
> найденных passages. Цитируй конкретные шаги из passages, не выдумывай.»

### 5. Скилл `obsidian` (уже стоит)

Используется для:
- Чтения vault (в ingest.py)
- Записи новых заметок (через тулы obsidian-skill, не agent tools)

## Поток данных (user query)

```
User: "Маша, что я делал с WireGuard в марте?"
  ↓
Agent (thinking): "прошлый опыт" → search_personal_kb
  ↓
search_personal_kb(query="WireGuard setup март", top_k=5)
  ↓
HTTP POST /v1/passages/search
  ↓
letta-server: passages из source "personal_kb" (vault + extracted chats)
  ↓
Agent: цитирует passages с шагами
  ↓
User: "WireGuard: 1. apt install..., 2. wg genkey..., 3. ..."
```

## Extract schema (LLM-промпт)

В extract pipeline используется промпт:

```
Ты — extract agent. Прочитай сессию чата. Выдели ТОЛЬКО успешный
путь Игоря — команды, шаги, решения, которые привели к результату.
Отбрось:
- отвлечения в смежные темы
- неудачные попытки (если есть успешная замена)
- small talk, приветствия
- дублирование

Формат ответа: YAML frontmatter + markdown шаги.
- source: chat
- date: <ISO date>
- session_topic: <короткая тема>
- success_path: true

Затем:
# <Topic>
1. <шаг>
2. <шаг>
...

Если сессия не имеет успешного пути (только отвлечения, ошибки), верни null.
```

## Error handling

- Vault не существует → exit 1 с понятной ошибкой
- Letta server недоступен → 3 retry с exponential backoff, потом exit
- LLM extract упал на конкретном чанке → пропустить chunk, залогировать, продолжить
- Source уже существует, `--create` не указан → переиспользовать
- Пустой vault / нет чатов → создать пустой source, exit 0

## Безопасность

- API-ключи — из env: `LETTA_API_KEY` (letta-server), `OPENCODE_GO_API_KEY` (litellm для extract)
- `LETA_BASE_URL=http://localhost:8283` (default)
- Файлы vault не отправляются наружу — extract через локальный litellm
- Скрипт не модифицирует vault, только читает

## Удаление / откат

- Скрипт: `rm scripts/ingest.py`, удалить cron-задачу
- Тул: PATCH агента без тула `search_personal_kb`
- Persona: PATCH без нового правила
- Source: `DELETE /v1/sources/{id}`

## Тестирование

- **Ручной ingest**:
  ```
  python3 scripts/ingest.py --vault ~/ObsidianVault --create --source personal_kb_test
  ```
  Ожидаем: source создан, файлы загружены, passages проиндексированы
- **RAG-поиск**:
  ```
  curl POST /v1/passages/search -d '{"query": "WireGuard", "limit": 3}'
  ```
  Ожидаем: список релевантных passages
- **Agent end-to-end**:
  - Спросить Машу: "что я делал с WireGuard?"
  - Ожидаем: ответ с цитатами из passages
- **Cron**: дождаться 2:00, проверить логи ingest

## Что НЕ входит в MVP

- Telegram-каналы ingestion (будущее)
- Audio podcast (issue letta-d1e)
- Multi-vault / multi-source (один source пока)
- Per-chat filtering при поиске (только общий `personal_kb`)
- Incremental ingest (только полная переиндексация)
- UI для ingest (только CLI)
