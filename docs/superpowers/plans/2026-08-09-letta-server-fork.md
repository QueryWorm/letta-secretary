# letta-server fork (fix RAG search) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Собрать свой `letta-server:custom` образ с патчем `request_embeddings` (upstream bug) и подключить его через docker-compose вместо `letta/letta:latest`, чтобы работал RAG-поиск.

**Architecture:** Custom Dockerfile с `FROM letta/letta:latest` + Python-патч который заменяет `raise NotImplementedError` в `llm_client_base.py:339` на fallback к `OpenAIClient.request_embeddings`. Дополнительно: clear `__pycache__` + `compileall` (защита от stale bytecode). Build: локальный `docker compose build`, image тегается `letta-server:custom`.

**Tech Stack:** Python 3.11 (внутри letta/letta:latest), Docker build (multi-stage COPY + RUN), letta-server REST API для тестов.

## Global Constraints

- Base image: `letta/letta:latest` (upstream)
- Patch target: `/app/letta/llm_api/llm_client_base.py:339`
- Patch replacement: `from letta.llm_api.openai_client import OpenAIClient; return await OpenAIClient().request_embeddings(texts, embedding_config)`
- Custom image tag: `letta-server:custom` (local, no push)
- Cache cleanup: `find /app/letta -name __pycache__ -type d -exec rm -rf {} +`
- Recompile: `python3 -m compileall -q /app/letta`
- docker-compose: `letta-server` service uses `image: letta-server:custom` + `build: context: ./letta-server`
- No API keys in patch (uses env already in compose)
- Patch is idempotent: detects already-patched state, exits 0
- Backup before patch: `llm_client_base.py.bak` in same dir
- All RAG search tests must pass after build

## File Structure

| File | Responsibility |
|---|---|
| `letta-server/patches/fix-embeddings.py` | Python patch script, idempotent |
| `letta-server/Dockerfile` | Build from letta/letta:latest + apply patch + clear cache |
| `docker-compose.yml` | Modify letta-server service: add build, change image |
| `docs/superpowers/specs/2026-08-09-letta-server-fork.md` | Spec (already exists, commit 8e636e2) |

---

### Task 1: Patch script + Dockerfile + build image

**Files:**
- Create: `/home/katya/letta/letta-server/patches/fix-embeddings.py`
- Create: `/home/katya/letta/letta-server/Dockerfile`

**Interfaces:**
- Produces: `letta-server:custom` docker image
- Patch script idempotent: handles already-patched case
- Dockerfile: minimal, only COPY + RUN

- [ ] **Step 1: Write `letta-server/patches/fix-embeddings.py`**

```python
"""Fix upstream letta bug: LLMClientBase.request_embeddings raises NotImplementedError.

Replaces the body with a fallback to OpenAIClient.request_embeddings, which is
the working implementation for OpenAI-compatible embedding endpoints (including our litellm).

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
    # Check if already patched by looking for fallback signature in the function body
    if "request_embeddings" in s:
        # Find the request_embeddings method
        idx = s.find("async def request_embeddings")
        if idx >= 0:
            # Look at next 2000 chars for OpenAIClient fallback
            snippet = s[idx:idx + 2000]
            if "from letta.llm_api.openai_client import OpenAIClient" in snippet:
                print("OK: already patched")
                sys.exit(0)
    raise SystemExit(f"ERROR: request_embeddings block not found in {p}")

bak = p.with_suffix(p.suffix + ".bak")
if not bak.exists():
    bak.write_text(s)
p.write_text(s.replace(OLD, NEW, 1))
print("OK: fix-embeddings patch applied")
```

- [ ] **Step 2: Write `letta-server/Dockerfile`**

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

- [ ] **Step 3: Build the custom image**

```bash
cd /home/katya/letta
docker compose build letta-server 2>&1 | tail -20
```

Expected: build completes successfully, image tagged as `letta-server:custom`. Output should include "OK: fix-embeddings patch applied" from the patch script.

- [ ] **Step 4: Verify image exists and patch was applied**

```bash
docker images | grep letta-server
# Should show: letta-server custom <hash> ...
docker run --rm letta-server:custom python3 -c "
with open('/app/letta/llm_api/llm_client_base.py') as f:
    s = f.read()
idx = s.find('async def request_embeddings')
snippet = s[idx:idx+2000]
assert 'OpenAIClient' in snippet, 'patch not applied'
print('OK: patch verified')
"
```

Expected: `OK: patch verified` (patch is in the image filesystem).

- [ ] **Step 5: Commit**

```bash
cd /home/katya/letta
git add letta-server/patches/fix-embeddings.py letta-server/Dockerfile
git commit -m "feat(letta-server): fork with fix-embeddings patch for request_embeddings"
```

---

### Task 2: docker-compose switch + e2e RAG search

**Files:**
- Modify: `/home/katya/letta/docker-compose.yml` (letta-server service)

**Interfaces:**
- docker-compose `letta-server` uses `image: letta-server:custom` + `build: context: ./letta-server`
- RAG search endpoint returns 200 with passages (not 500)
- LLM endpoints still work (regression check)

- [ ] **Step 1: Modify `docker-compose.yml` letta-server service**

In `/home/katya/letta/docker-compose.yml`, find the `letta-server:` block. Change:

```yaml
  letta-server:
    image: letta/letta:latest
```

To:

```yaml
  letta-server:
    image: letta-server:custom
    build:
      context: ./letta-server
      dockerfile: Dockerfile
```

Keep all other fields unchanged (env, volumes, depends_on, ports, restart).

- [ ] **Step 2: Stop current letta-server and start with custom image**

```bash
cd /home/katya/letta
docker compose up -d --force-recreate --no-deps letta-server 2>&1 | tail -5
```

Expected: container recreated, image shows `letta-server:custom`.

- [ ] **Step 3: Wait for ready and verify version**

```bash
sleep 25
docker compose ps 2>&1 | grep letta-server
docker compose logs letta-server --since 30s 2>&1 | grep -iE "ready|migrate|error" | tail -10
```

Expected: container Up, no migration errors, `Readiness telemetry transition: warming -> ready` log line.

- [ ] **Step 4: RAG search end-to-end test**

```bash
# Create test source
SID=$(curl -sS -X POST "http://localhost:8283/v1/sources/" \
    -H "Authorization: Bearer ${LETTA_API_KEY:-sk-let-Mzg3ZWUwZWEtYmI1ZS00Mzc1LTg2MWEtNmU5ODQ4OWFmNzBmOmQ4NjViYjA1LThmZWUtNGUwMC1hYmU2LTkyZThjZjVhNTFhMw==}" \
    -H "Content-Type: application/json" \
    -d '{"name":"rag-fix-test","embedding":"openai","embedding_chunk_size":300,"embedding_model":"text-embedding-3-large","embedding_endpoint":"http://litellm:4000","embedding_dim":3072}' | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")
echo "Source: $SID"

# Upload a test file
echo "# Test\n\nThis is a test passage about WireGuard setup on Ubuntu." > /tmp/test-rag.md
curl -sS -X POST "http://localhost:8283/v1/sources/${SID}/upload" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" \
    -F "file=@/tmp/test-rag.md" \
    -F "duplicate_handling=replace" 2>&1 | head -c 100
echo
sleep 3

# Search — the critical test
echo "=== RAG SEARCH ==="
curl -sS -X POST "http://localhost:8283/v1/passages/search" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"WireGuard setup\",\"limit\":3,\"source_id\":\"${SID}\"}" -w "\nHTTP %{http_code}\n" 2>&1 | head -c 1000
echo

# Cleanup
curl -sS -X DELETE "http://localhost:8283/v1/sources/${SID}" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" 2>&1 | head -c 50
```

Expected: `HTTP 200` and JSON array with passages. NOT `HTTP 500`. The critical test is that the search returns 200 — the content can be anything as long as it's not an error.

- [ ] **Step 5: Regression — verify LLM still works**

```bash
curl -sS -X POST "http://localhost:8283/v1/agents/agent-d622b194-88c6-4972-8421-fda92c1753a0/messages" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${LETTA_API_KEY}" \
    -d '{"messages":[{"role":"user","content":"ping"}]}' 2>&1 | head -c 200
echo
sleep 8
curl -sS "http://localhost:8283/v1/agents/agent-d622b194-88c6-4972-8421-fda92c1753a0/messages?limit=2" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for m in d[:3]:
    print(m.get('date'),'|',m.get('message_type'))
" 2>&1 | head -5
```

Expected: agent has a recent `assistant_message` or `tool_return_message` after the user message — LLM call still works.

- [ ] **Step 6: Commit**

```bash
cd /home/katya/letta
git add docker-compose.yml
git commit -m "feat(letta-server): switch to custom build with embedding fix"
```

---

## Self-Review

**Spec coverage:**
- Patch script `fix-embeddings.py` (idempotent, .bak backup) → Task 1 Step 1 ✓
- Dockerfile (FROM latest + COPY + RUN + clear cache + compileall) → Task 1 Step 2 ✓
- `image: letta-server:custom` + `build:` → Task 2 Step 1 ✓
- RAG search returns 200 (not 500) → Task 2 Step 4 ✓
- LLM regression check → Task 2 Step 5 ✓
- Idempotency: re-build doesn't fail → Step 1 logic handles already-patched ✓
- Backup before patch → `.bak` write in Step 1 ✓
- Cache cleanup + recompile → Dockerfile Steps 3-4 ✓
- Error handling: not found → SystemExit; already patched → exit 0 ✓
- Test: build success, image exists, e2e RAG search 200 ✓
- Удаление / откат — documented in spec, not in plan tasks (operator decision) ✓
- Известные риски — noted in spec ✓

**Placeholder scan:** No TBD/TODO. All steps have specific commands and code.

**Type consistency:**
- `fix-embeddings.py` reads `/app/letta/llm_api/llm_client_base.py` (default), accepts argv[1] override ✓
- `OLD` and `NEW` blocks match the actual `letta_client_base.py:325-339` shape (verified from upstream source) ✓
- docker-compose changes only touch `image:` and add `build:` block ✓
- Test commands use `LETTA_API_KEY` from env with default value matching the existing token in the project ✓
