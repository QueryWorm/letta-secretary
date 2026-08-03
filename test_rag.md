# Инфраструктура Letta Code

## Сервер
Ubuntu на Supermicro X10DRL-C Xeon, 32Gb RAM, 29Gb диска. Путь проекта — ~/letta. Шелл zsh, таймзона Europe/Kyiv.

## Стек сервисов

### letta-db
Postgres с расширением pgvector. Хранит состояние агента, память, тудушку (таблица lettabot_todos) и теперь RAG-документы через Folders API.

### letta-server
Letta App Server, порт 8283. Основная точка входа для агента igor_secretary_or.

### lettabot
Мультиканальный бридж для Telegram и WhatsApp, submodule letta-ai/lettabot. Собран из ./lettabot, подключается к letta-db напрямую через pg-клиент для тудушки.

### litellm
Прокси-роутер на порту 4000. Модель secretary-model работает через два бэкенда: Cerebras gemma-4-31b и Gemini gemini-2.5-flash. SambaNova исключён из-за галлюцинаций tool-calling под нагрузкой.

## Известные проблемы

### Approval-конфликт
После ухода run в requires_approval все последующие сообщения агенту зависают без ответа и без ошибки в логах. Recovery срабатывает только при пересоздании контейнера lettabot.

### Тудушка на файлах
Раньше манеж тудушек хранился в JSON на диске контейнера, что приводило к потере задач при пересоздании. Полностью переписано на Postgres.

## Тудушка
Таблица lettabot_todos хранит id, agent_key, text, category, urgent, important, created, due, snoozed_until, recurring, completed, completed_at. Модель сама выводит category, urgent и important из контекста сообщения.
