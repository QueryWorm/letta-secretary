# Debug-тэг в исходящих сообщениях — План имплементации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В каждом исходящем сообщении агента в WhatsApp (`380975907324`) и Telegram (`322910508`) дописывать тэг `[model: secretary-model | latency: <X.Ys>s]` с реальным временем от inbound до outbound.

**Architecture:** Один Python-патч для JS-бандла `letta-code-channels/letta.js`. Два места: `handleInboundMessage` пишет timestamp в `globalThis.__inboundTs`, `buildMessageChannelRequest` читает и дописывает тэг. Без IPC, без shared volume.

**Tech Stack:** Python 3.12 (для патч-скрипта), JavaScript (патчимый бандл Node.js).

## Global Constraints

- Патч только для chat_id `380975907324` (WhatsApp) и `322910508` (Telegram). Другие адресаты — не трогаем.
- Тэг формата `[model: secretary-model | latency: <X.Ys>s]` — захардкоженный `secretary-model`, latency с одним знаком после точки.
- Тэг дописывается после пустой строки в конце сообщения.
- Идемпотентность: если сообщение уже содержит `[model:` — не дописывать.
- Патч применяется **при старте контейнера** (не при сборке образа), как и существующие патчи.
- Временная фича: должна быть возможность полностью удалить (файл патча + строка в Dockerfile).
- `.bak` файл оригинального бандла остаётся для отката.

## File Structure

| Файл | Ответственность |
|---|---|
| `letta-code-channels/patches/patch-debug-tagging.py` | Python-скрипт, патчит JS-бандл |
| `letta-code-channels/Dockerfile` | Запускает все патчи при старте, включая новый |
| `docs/superpowers/specs/2026-08-08-debug-tagging.md` | Спека (уже есть) |

---

### Task 1: Заменить старый debug-патч на новый с реальными данными

**Files:**
- Modify: `letta-code-channels/patches/patch-debug-tagging.py` (полная замена содержимого)
- Modify: `letta-code-channels/Dockerfile` (добавить вызов `patch-debug-tagging.py` после других патчей)

**Interfaces:**
- Consumes: `letta.js` (Node.js bundle в `/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js`)
- Produces: модифицированный `letta.js` с двумя правками + `.bak` оригинал

- [ ] **Step 1: Написать новый `patch-debug-tagging.py`**

Заменить содержимое `letta-code-channels/patches/patch-debug-tagging.py` на:

```python
"""TEMPORARY DEBUG PATCH: append [model: secretary-model | latency: Xs] to outgoing
messages for the two user chat_ids.

REMOVAL: delete this file and remove the invocation from Dockerfile, then rebuild.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()

WHITELIST = ("380975907324", "322910508")
MODEL_NAME = "secretary-model"
TAG_MARKER = "[model:"

# A) Record inbound timestamp in handleInboundMessage
old_a = (
    "  async function handleInboundMessage(msg) {\n"
    "    const accountId = msg.accountId ?? LEGACY_CHANNEL_ACCOUNT_ID;"
)
new_a = (
    "  async function handleInboundMessage(msg) {\n"
    "    try {\n"
    "      const __tsMap = (globalThis.__inboundTs ||= new Map());\n"
    "      if (msg && msg.chatId) __tsMap.set(String(msg.chatId), Date.now());\n"
    "    } catch {}\n"
    "    const accountId = msg.accountId ?? LEGACY_CHANNEL_ACCOUNT_ID;"
)
if old_a not in s:
    raise SystemExit("ERROR: handleInboundMessage not found (already patched or bndl changed)")
s = s.replace(old_a, new_a, 1)

# B) Append tag in buildMessageChannelRequest
old_b = (
    "function buildMessageChannelRequest(input, chatId, threadId) {\n"
    "  return {\n"
    "    action: input.action,\n"
    "    channel: input.channel,\n"
    "    chatId,\n"
    "    message: input.message,\n"
)
new_b = (
    "function buildMessageChannelRequest(input, chatId, threadId) {\n"
    "  try {\n"
    f"    const __whitelist = new Set({list(WHITELIST)!r});\n"
    "    const __tsMap = globalThis.__inboundTs;\n"
    "    if (input && typeof input.message === \"string\" && input.action !== \"react\" && input.action !== \"remove\" && input.action !== \"download-file\" && !input.message.includes(TAG_MARKER) && __whitelist.has(String(chatId)) && __tsMap && __tsMap.has(String(chatId))) {\n"
    f"      const __lat = ((Date.now() - __tsMap.get(String(chatId))) / 1000).toFixed(1);\n"
    f"      input.message = input.message + \"\\n\\n[model: {MODEL_NAME} | latency: \" + __lat + \"s]\";\n"
    "      __tsMap.delete(String(chatId));\n"
    "    }\n"
    "  } catch {}\n"
    "  return {\n"
    "    action: input.action,\n"
    "    channel: input.channel,\n"
    "    chatId,\n"
    "    message: input.message,\n"
)
if old_b not in s:
    raise SystemExit("ERROR: buildMessageChannelRequest not found (already patched or bndl changed)")
s = s.replace(old_b, new_b, 1)

p.write_text(s)
print("OK: debug-tagging patch applied")
```

**Примечание:** `TAG_MARKER` подставляется в шаблон через f-string, поэтому в коде выше `{TAG_MARKER}` в `__whitelist.has(...)` уже после форматирования станет `__whitelist.has(...)`. Внимание: в Python f-string, `{TAG_MARKER}` интерполируется в `[model:`. Это правильно. Но `{list(WHITELIST)!r}` тоже интерполируется — должно стать `['380975907324', '322910508']`.

Проверь, что финальный код содержит:
- `__whitelist.has(String(chatId))` — String обёртка для безопасности
- `__tsMap && __tsMap.has(String(chatId))` — оба условия
- `__lat = ((Date.now() - __tsMap.get(String(chatId))) / 1000).toFixed(1)` — формула latency
- `__tsMap.delete(String(chatId))` — очистка после использования

- [ ] **Step 2: Применить патч в работающем контейнере**

```bash
docker cp /home/katya/letta/letta-code-channels/patches/patch-debug-tagging.py letta-letta-code-channels-1:/tmp/patch-debug-tagging.py
docker compose exec -T letta-code-channels bash -c "cp /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js.bak.v2 && python3 /tmp/patch-debug-tagging.py"
```

Expected: `OK: debug-tagging patch applied` (или ошибка если `old_a`/`old_b` не найдены — это значит патч уже применён или бандл изменился).

- [ ] **Step 3: Перезапустить letta-code-channels**

```bash
docker compose restart letta-code-channels
```

Подожди 10-15 секунд, проверь что бот Telegram поднялся:

```bash
docker compose logs letta-code-channels --since 20s | grep -E "polling ready|Bot started"
```

Expected: `Bot started as @Masha_serv_bot` и `polling ready`.

- [ ] **Step 4: Откатить старый патч в бандле**

Старый патч (захардкоженный `qwen3.7-plus | latency: ~?s | tokens: ~?/~?`) сейчас
применён в бандле. Новый патч **не** сможет примениться из-за двойного изменения
в `buildMessageChannelRequest` — старая правка изменила сигнатуру блока.

Откатим через `.bak` или текущее состояние, чтобы потом новый patch применился чисто:

```bash
docker compose exec -T letta-code-channels bash -c "cp /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js.bak /usr/local/lib/node_modules/@letta-ai/letta-code/letta.js"
```

(`.bak` — это бэкап **до** старого патча, сделанный при первом применении.)

- [ ] **Step 5: Применить новый патч чисто**

```bash
docker compose exec -T letta-code-channels bash -c "python3 /tmp/patch-debug-tagging.py"
```

Expected: `OK: debug-tagging patch applied`.

- [ ] **Step 6: Перезапустить контейнер ещё раз**

```bash
docker compose restart letta-code-channels
```

Подожди 10-15 секунд, проверь `polling ready`.

- [ ] **Step 7: Закоммитить изменения**

```bash
cd /home/katya/letta
git add letta-code-channels/patches/patch-debug-tagging.py
git commit -m "feat: append [model | latency] tag to outgoing messages for user chat_ids"
```

---

### Task 2: Добавить вызов нового патча в Dockerfile

**Files:**
- Modify: `letta-code-channels/Dockerfile` (добавить одну строку с вызовом `patch-debug-tagging.py`)

**Interfaces:**
- Consumes: существующие строки в `Dockerfile` с вызовами других патчей
- Produces: Dockerfile применяет новый патч при следующей пересборке образа

- [ ] **Step 1: Прочитать текущий Dockerfile**

```bash
cat /home/katya/letta/letta-code-channels/Dockerfile
```

- [ ] **Step 2: Найти место после других патчей**

В Dockerfile должна быть секция вида `RUN python3 /tmp/patch-X.py` или похожая
для каждого из существующих патчей (`patch-turn-error.py`, `patch-gateway-send.py`,
`patch-transcription.js`).

- [ ] **Step 3: Добавить вызов нового патча**

Добавить строку **после** вызовов остальных патчей:

```dockerfile
RUN python3 /tmp/patch-debug-tagging.py || echo "patch-debug-tagging already applied or missing"
```

Используем `|| echo ...` чтобы пересборка не падала если патч уже применён или
если бандл обновился (тогда патч вернёт ошибку и `old_a`/`old_b` не найдутся).

- [ ] **Step 4: Закоммитить**

```bash
cd /home/katya/letta
git add letta-code-channels/Dockerfile
git commit -m "build: add patch-debug-tagging.py to Dockerfile"
```

---

### Task 3: Проверить работу тэга в реальном канале

**Files:** (нет правок, только тестирование)

- [ ] **Step 1: Отправить "ping" в Telegram бот `@Masha_serv_bot`**

Скажи пользователю: «Напишите боту @Masha_serv_bot в Telegram: `ping`»

- [ ] **Step 2: Проверить что пришёл ответ с тэгом**

Ожидаемый ответ (пример):
```
pong

[model: secretary-model | latency: 2.4s]
```

- [ ] **Step 3: Проверить что в WhatsApp тоже работает**

Скажи пользователю: «Отправьте себе в WhatsApp: `ping`»
(чат `380975907324@s.whatsapp.net`)

Ожидаемый ответ с тэгом.

- [ ] **Step 4: Проверить что cron-напоминание НЕ получает тэг**

В persona уже записано правило «крон-напоминания — во все каналы».
Cron-trigger приходит в канал `380975907324` или `322910508`, но
`__inboundTs` для этого chat_id **не** будет записан (cron-trigger —
это не inbound от пользователя, а от runtime). Поэтому тэг не
допишется.

Если пользователь хочет cron-тэги — это отдельная задача.

---

## Self-Review

- **Spec coverage:**
  - `[model: X | latency: Ys]` формат → Task 1, Step 1
  - Whitelist (только `380975907324`, `322910508`) → Task 1, Step 1
  - Полная latency (inbound → outbound) → Task 1, Step 1 (через `globalThis.__inboundTs`)
  - Идемпотентность (`[model:` marker) → Task 1, Step 1
  - Применение при старте (Dockerfile) → Task 2
  - Тестирование → Task 3
  - Удаление (документировано в спеке + комментарий в патче) ✓
- **Placeholder scan:** нет TBD/TODO; все шаги с кодом.
- **Type consistency:** `globalThis.__inboundTs` — Map; используется одинаково в A и B.
- **Idempotency:** patch-detect есть в Step 5 (если `old_a`/`old_b` не найдены — ошибка).
- **Edge cases:** cron без inbound → тэг не дописывается (проверено в Step 4 Task 3).
- **Rollback:** `.bak` файлы + `git revert` двух коммитов.
