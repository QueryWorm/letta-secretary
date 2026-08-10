# Дизайн: периодический retry неработающих каналов

Дата: 2026-08-09
Проект: letta-code-channels (контейнер `letta-letta-code-channels-1`)

## Проблема

Блокировки сети (например, к api.telegram.org) то включаются, то отключаются.
Каналы стартуют один раз при старте процесса (`init_channels` →
`initializeChannels`). При недоступности канала он просто пропускается —
gateway живёт (патч `patch-allow-startup-errors.py`), но адаптер не стартует.
Retry-цикла в коде нет, поэтому после снятия блокировки канал сам не поднимается.

## Решение

Патч `letta.js` (по схеме существующих патчей в `patches/`), встраивается в
`startLocalChannelGateway` сразу после `initializeChannels`, где доступны
`registry2`, `options3`, `logChannelStartup`, `formatChannelStartupError`,
а также module-level функции `listChannelAccounts`, `hydrateChannelAccountSecrets`,
`shouldRestoreChannelAccountForAgentScope`.

### Логика

Периодический sweep каждые 5 минут (настраивается env
`LETTA_CHANNEL_RETRY_INTERVAL_MS`, по умолчанию 5 * 60 * 1000):

1. Для каждого `channelId` из `options3.channelNames`:
   - `hydrateChannelAccountSecrets(channelId)`
   - аккаунты = `listChannelAccounts(channelId)` фильтр `enabled` и restore-scope
2. Для каждого аккаунта:
   - если `registry2.getAdapter(channelId, accountId)?.isRunning()` → пропустить
     (живой канал НЕ трогаем: `startChannelAccount` перезапускает работающий адаптер)
   - иначе `registry2.startChannelAccount(channelId, accountId)` в отдельном
     try/catch — ошибка только логируется, процесс не падает
3. Внешний try/catch на весь sweep + флаг `retryRunning` от наложения тиков

## Гарантии

- Сервер не падает: все вызовы в try/catch, исключения только логируются.
- Живые каналы не перезапускаются: проверка `isRunning()` перед стартом.
- Интервал конфигурируется через env.

## Тестирование

1. Пересобрать образ, пересоздать контейнер.
2. Убедиться, что WhatsApp остался живым (патч не трогает работающие адаптеры).
3. В логах при недоступном Telegram — `[Channels] retrying telegram/... (not running)`
   каждые 5 минут, RestartCount = 0.
