# letta-server fork (fix RAG search) — Дизайн

**Дата:** 2026-08-09
**Статус:** утверждён
**Объём:** собрать свой docker-образ `letta-server:custom` с патчем upstream-бага `request_embeddings`, чтобы работал `POST /v1/passages/search` (RAG-поиск).

## Цель

Сейчас в `letta/letta:latest` (upstream) `POST /v1/passages/search` возвращает HTTP 500 с `NotImplementedError: request_embeddings`. Это блокирует весь knowledge pipeline (RAG по vault). Upstream issue #3122 закрыт 2026-02-09, но фикс не дошёл до main (проверено 2026-08-09).

Решение: собрать свой образ `letta-server:custom` на базе `letta/letta:latest` с патчем `llm_client_base.py:339`, который заменяет `raise NotImplementedError` на fallback к `OpenAIClient.request_embeddings`. Дополнительно: очистить `__pycache__` и пересобрать `.pyc` (защита от stale bytecode).

## Зачем

- Knowledge pipeline (RAG по vault) заблокирован без этого
- Issue `letta-2hn` (P1, BLOCKING) tracked в bd
- Другой workaround (per-chat search, turbopuffer) не подходит — мы используем native pgvector + OpenAI-compatible embedding

## Архитектура

```
letta/letta:latest (upstream, сломан — request_embeddings бросает NotImplementedError)
  ↓ FROM
letta-secretary/letta-server:custom
  ↓ RUN
patches/fix-embeddings.py
  - replace /app/letta/llm_api/llm_client_base.py:339
  - raise NotImplementedError → OpenAIClient().request_embeddings(texts, embedding_config)
  ↓ RUN
rm -rf /app/letta/**/__pycache__ (clear stale bytecode)
  ↓ RUN
python3 -m compileall /app/letta (rebuild .pyc)
  ↓ docker compose up -d letta-server
```

После фикса:
- `LLMClient.create(openai)` → `OpenAIClient` (как и раньше)
- `OpenAIClient.request_embeddings(texts, embedding_config)` — **теперь** правильно вызывается
- Внутри `OpenAIClient`: HTTP POST к `embedding_endpoint` (наш `http://litellm:4000`) — **работает**

## Подход

**Patch script (Python)** — consistent с существующими патчами в проекте:
- `letta-code-channels/patches/patch-debug-tagging.py`
- `letta-code-channels/patches/patch-gateway-send.py`
- `letta-code-channels/patches/patch-voice-attachment.py` (revert'нут, но pattern тот же)

Патч: `read_text` → `replace` (idempotent) → `write_text` + `.bak` backup. В Dockerfile: `COPY` + `RUN` + clear cache + compileall.

## Компоненты

### 1. `letta-server/patches/fix-embeddings.py` (новый)

```python
"""Fix upstream letta bug: LLMClientBase.request_embeddings raises NotImplementedError.

Replaces the body with a fallback to OpenAIClient.request_embeddings, which is the
working implementation for OpenAI-compatible embedding endpoints (including our litellm).

Idempotent: if already patched, exits 0.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/app/letta/llm_api/llm_client_base.py")
s = p.read_text()

OLD = '''    @abstractmethod
    async def request_embeddings(self, texts: List[str], embedding_config: EmbeddingConfig) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts (List[str]): List of texts to generate embeddings for.
            embedding_config (EmbeddingConfig): Configuration for the embedding model.

        Returns:
            embeddings (List[List[float]]): List of embeddings for the input texts.
        """
        raise NotImplementedError'''

NEW = '''    @abstractmethod
    async def request_embeddings(self, texts: List[str], embedding_config: EmbeddingConfig) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts (List[str]): List of texts to generate embeddings for.
            embedding_config (EmbeddingConfig): Configuration for the embedding model.

        Returns:
            embeddings (List[List[float]]): List of embeddings for the input texts.
        """
        # PATCH (letta-secretary): fallback to OpenAIClient (fix for upstream bug,
        # issue #3122 closed but fix not in main). Works for OpenAI-compatible
        # embedding endpoints (litellm, etc).
        from letta.llm_api.openai_client import OpenAIClient
        return await OpenAIClient().request_embeddings(texts, embedding_config)'''

if OLD not in s:
    if "from letta.llm_api.openai_client import OpenAIClient" in s and "raise NotImplementedError" not in s.split("def request_embeddings")[1].split("def ")[0]:
        print("OK: already patched")
        sys.exit(0)
    raise SystemExit("ERROR: request_embeddings block not found in " + str(p))

bak = p.with_suffix(p.suffix + ".bak")
if not bak.exists():
    bak.write_text(s)
p.write_text(s.replace(OLD, NEW, 1))
print("OK: fix-embeddings patch applied")
```

### 2. `letta-server/Dockerfile` (новый)

```dockerfile
FROM letta/letta:latest

# Patch the upstream bug in request_embeddings (issue #3122 closed but not in main)
COPY patches/fix-embeddings.py /tmp/fix-embeddings.py
RUN python3 /tmp/fix-embeddings.py

# Clear stale __pycache__ (defensive: in case .pyc is older than .py)
RUN find /app/letta -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

# Rebuild .pyc from current .py
RUN python3 -m compileall -q /app/letta || true
```

### 3. `docker-compose.yml` (modify)

В `letta-server` service:
```yaml
  letta-server:
    image: letta-server:custom
    build:
      context: ./letta-server
      dockerfile: Dockerfile
    # ... rest unchanged
```

`build:` + `image:` даёт тег `letta-server:custom` и кеширует в `docker images`.

## Поток данных

```
docker compose build letta-server
  → reads ./letta-server/Dockerfile
  → FROM letta/letta:latest (cached or pulled)
  → COPY patches/fix-embeddings.py /tmp/
  → RUN python3 /tmp/fix-embeddings.py
    → reads /app/letta/llm_api/llm_client_base.py
    → replaces request_embeddings block
    → writes .bak + patched
  → RUN find ... __pycache__ -exec rm
  → RUN python3 -m compileall
  → tags image as letta-server:custom

docker compose up -d letta-server
  → starts container from letta-server:custom
  → request_embeddings now works (fallback to OpenAIClient)
  → POST /v1/passages/search returns 200 + passages
```

## Error handling

- **Patch not found** (already patched or upstream fix): `fix-embeddings.py` exits 0 with "OK: already patched"
- **Multiple matches** (regex ambiguous): fail with clear error
- **Build fail** (network, missing patches/): `docker compose build` errors out, no image created
- **Stale .pyc** (file change without recompile): `compileall` re-creates fresh .pyc

## Тестирование

- **Build**: `docker compose build letta-server` → success
- **Container start**: `docker compose up -d letta-server` → healthy через 30s
- **RAG search test**: создать source, загрузить файл, найти → должен вернуть 200 + passages
- **Regression**: обычные LLM-запросы работают (qwen3.7-plus, etc)
- **Idempotency**: `docker compose build` второй раз → "OK: already patched", не падает

## Удаление / откат

- `docker compose down`
- `docker rmi letta-server:custom`
- В `docker-compose.yml` вернуть `image: letta/letta:latest`
- Удалить `letta-server/` директорию
- Если upstream починит — просто пересобрать на `letta/letta:latest` (наш patch будет no-op)

## Что НЕ входит

- Другие фиксы letta (только request_embeddings)
- Push в Docker Hub / GHCR (локальная сборка)
- CI/CD
- Multi-provider embedding (только OpenAI-compatible)
- Автообновление при upstream-фиксе

## Известные риски

- **Upstream fix**: если letta починит в main, наш patch станет no-op. Мониторим, при необходимости — откатываем.
- **Ложный fix**: если base class должен бросать NotImpl для некоторых провайдеров, наш fallback может поломать. В MVP — только OpenAI-compatible, OK.
- **Build кеш**: если Dockerfile меняется, нужно `docker compose build --no-cache`. Не критично.

## План реализации

Создам в `writing-plans` skill после твоего одобрения спеки.
