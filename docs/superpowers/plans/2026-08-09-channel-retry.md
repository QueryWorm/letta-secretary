# Channel Retry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Периодический retry подъёма неработающих каналов letta-code-channels (раз в 5 мин), не роняя процесс и не трогая живые каналы.

**Architecture:** Python-патч `letta.js` по схеме существующих патчей в `patches/`; встраивает `setInterval`-sweep в `startLocalChannelGateway` сразу после `initializeChannels`. Sweep перебирает каналы из `channelNames`, пропускает работающие адаптеры (`isRunning()`), стартует неработающие через `startChannelAccount` в try/catch.

**Tech Stack:** Python 3 (патч-скрипт), JavaScript (Node 22, letta-code 0.30.3), Docker.

## Global Constraints

- Интервал retry: `LETTA_CHANNEL_RETRY_INTERVAL_MS`, по умолчанию `5 * 60 * 1000` (5 мин).
- Живые каналы НЕ перезапускаются: `startChannelAccount` перезапускает работающий адаптер, поэтому перед стартом обязательна проверка `registry2.getAdapter(channelId, accountId)?.isRunning()`.
- Все вызовы сетевых/стартовых операций — в try/catch; исключения только логируются через `console.error` + `logChannelStartup`. Процесс не падает.
- Патч-скрипт завершается с ненулевым кодом (`raise SystemExit`) при отсутствии якоря — сборка образа падает, а не молча пропускает патч.

---

### Task 1: Создать патч-скрипт `patch-channel-retry.py`

**Files:**
- Create: `letta-code-channels/patches/patch-channel-retry.py`

**Interfaces:**
- Consumes: файл `/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js` (изменяется на месте).
- Produces: патч-скрипт, который добавляет в `startLocalChannelGateway` блок retry-sweep после инициализации каналов. Скрипт принимает путь к letta.js первым аргументом (default тот же путь), печатает `OK: channel retry patch applied`.

- [ ] **Step 1: Написать патч-скрипт**

```python
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js")
s = p.read_text()

# Anchor: the block after initializeChannels in startLocalChannelGateway.
old = """  const registry2 = getChannelRegistry();
  if (!registry2) {
    client.close();
    throw new Error("Channel registry did not initialize");
  }"""

new = old + """

  // PATCH (letta-secretary): periodically retry starting channels that did
  // not come up (e.g. Telegram API temporarily blocked). Never crashes the
  // gateway and never restarts already-running adapters.
  const retryIntervalMs = Number(process.env.LETTA_CHANNEL_RETRY_INTERVAL_MS || 5 * 60 * 1000);
  if (retryIntervalMs > 0 && options3.channelNames.length > 0) {
    let retryRunning = false;
    const retryChannels = async () => {
      if (retryRunning) return;
      retryRunning = true;
      try {
        for (const channelId of options3.channelNames) {
          try {
            await hydrateChannelAccountSecrets(channelId);
            const accounts = listChannelAccounts(channelId).filter(
              (account) => account.enabled && shouldRestoreChannelAccountForAgentScope(account, options3.restoreAgentScope)
            );
            for (const account of accounts) {
              const adapter = registry2.getAdapter(channelId, account.accountId);
              if (adapter?.isRunning()) continue;
              logChannelStartup(options3.logger, `retrying ${channelId}/${account.accountId} (not running)`);
              try {
                await registry2.startChannelAccount(channelId, account.accountId, { logger: options3.logger });
              } catch (error54) {
                const message = error54 instanceof Error ? error54.message : String(error54);
                console.error(`[Channels] Retry start failed for ${channelId}/${account.accountId}:`, message);
                logChannelStartup(options3.logger, `retry failed ${channelId}/${account.accountId}: ${message}`);
              }
            }
          } catch (error54) {
            const message = error54 instanceof Error ? error54.message : String(error54);
            console.error(`[Channels] Retry sweep failed for ${channelId}:`, message);
          }
        }
      } finally {
        retryRunning = false;
      }
    };
    setInterval(retryChannels, retryIntervalMs);
  }
"""

if old not in s:
    raise SystemExit("ERROR: channel registry init block not found")
p.write_text(s.replace(old, new, 1))
print("OK: channel retry patch applied")
```

- [ ] **Step 2: Проверить патч на копии текущего letta.js**

Копируем актуальный letta.js из контейнера и прогоняем патч локально:

```bash
docker cp letta-letta-code-channels-1:/usr/local/lib/node_modules/@letta-ai/letta-code/letta.js /tmp/opencode/letta-retry-test.js
python3 /home/katya/letta/letta-code-channels/patches/patch-channel-retry.py /tmp/opencode/letta-retry-test.js
node --check /tmp/opencode/letta-retry-test.js
```

Expected: `OK: channel retry patch applied`, затем `node --check` без вывода (синтаксис валиден).

- [ ] **Step 3: Проверить, что якорь встречается ровно один раз**

```bash
grep -c "Channel registry did not initialize" /tmp/opencode/letta-retry-test.js
```

Expected: `1` (якорь уникален и на месте; в `new` дубликат не добавляется — `s.replace(old, new, 1)` заменяет исходный блок на `new`, содержащий якорь один раз).

- [ ] **Step 4: Commit**

```bash
git add letta-code-channels/patches/patch-channel-retry.py
git commit -m "feat(channels): periodic retry for failed channel startup"
```

---

### Task 2: Подключить патч в Dockerfile

**Files:**
- Modify: `letta-code-channels/Dockerfile` (после блока `patch-allow-startup-errors.py`)

**Interfaces:**
- Consumes: `patches/patch-channel-retry.py` (создан в Task 1).
- Produces: образ, в котором letta.js содержит retry-патч.

- [ ] **Step 1: Добавить COPY+RUN для патча**

После строк:
```dockerfile
COPY patches/patch-allow-startup-errors.py /tmp/patch-allow-startup-errors.py
RUN python3 /tmp/patch-allow-startup-errors.py && rm /tmp/patch-allow-startup-errors.py
```
добавить:
```dockerfile
COPY patches/patch-channel-retry.py /tmp/patch-channel-retry.py
RUN python3 /tmp/patch-channel-retry.py && rm /tmp/patch-channel-retry.py
```

- [ ] **Step 2: Пересобрать образ**

```bash
cd /home/katya/letta
docker compose build letta-code-channels
```

Expected: сборка завершается успешно, в логе сборки — `OK: channel retry patch applied`.

- [ ] **Step 3: Commit**

```bash
git add letta-code-channels/Dockerfile
git commit -m "feat(channels): apply channel retry patch in image build"
```

---

### Task 3: Пересоздать контейнер и проверить

**Files:**
- Modify: `docker-compose.yml` (временное добавление env для ускоренной проверки)

**Interfaces:**
- Consumes: пересобранный образ из Task 2.
- Produces: доказательство, что sweep работает и процесс не падает.

- [ ] **Step 1: Временно ускорить retry для проверки**

В `docker-compose.yml` в сервис `letta-code-channels` добавить:
```yaml
    environment:
      - LETTA_CHANNEL_RETRY_INTERVAL_MS=10000
```
(чтобы увидеть sweep в логах за ~30 сек вместо 5 минут)

- [ ] **Step 2: Пересоздать контейнер**

```bash
cd /home/katya/letta
docker compose up -d --force-recreate letta-code-channels
```

- [ ] **Step 3: Проверить, что WhatsApp живой и telegram ретраится**

```bash
docker inspect -f '{{.RestartCount}}' letta-letta-code-channels-1
sleep 35
docker logs letta-letta-code-channels-1 --since 1m 2>&1 | grep -E "retrying|WhatsApp Connected|started adapter" | tail -20
```

Expected: RestartCount = 0; в логах есть `[Channels] retrying telegram/<id> (not running)`; WhatsApp-адаптер НЕ перезапускается (нет повторного `stopping existing adapter`/`starting adapter for whatsapp`).

- [ ] **Step 4: Вернуть интервал 5 минут**

Убрать строку `LETTA_CHANNEL_RETRY_INTERVAL_MS=10000` из `docker-compose.yml`, пересоздать контейнер заново:
```bash
docker compose up -d --force-recreate letta-code-channels
docker inspect -f '{{.RestartCount}}' letta-letta-code-channels-1
```
Expected: RestartCount = 0, WhatsApp Connected.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(channels): verify channel retry sweep, restore 5min interval"
```

---

## Self-Review

- **Spec coverage:** retry каждые 5 мин ✓ (Task 1, env default 5 мин), не роняет процесс ✓ (все try/catch, Task 1), не трогает живые каналы ✓ (проверка `isRunning()` + Task 3 Step 3), env-настройка интервала ✓, тест после пересборки ✓ (Task 3).
- **Placeholder scan:** нет TBD/TODO; все шаги содержат конкретный код и команды.
- **Type consistency:** в патче используются имена из letta.js: `options3.channelNames`, `options3.restoreAgentScope`, `options3.logger`, `registry2.getAdapter`, `registry2.startChannelAccount`, `listChannelAccounts`, `hydrateChannelAccountSecrets`, `shouldRestoreChannelAccountForAgentScope`, `logChannelStartup` — сверены с кодом letta.js 0.30.3 (проверено в контейнере).
