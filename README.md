# Romania Remote Job Monitor

Автоматический мониторинг удаленных вакансий для Румынии.

## Источники
- ejobs.ro
- bestjobs.ro
- hipo.ro
- remotive.com
- jobicy.com
- jobscollider.com

## Фильтры
- Только remote/online позиции
- IT + страховая сфера (не агент)
- Исключает вакансии с требованием Advanced/Fluent English

## Запуск
- Скрейпер запускается автоматически 4 раза в день через GitHub Actions (`.github/workflows/scraper.yml`)
- Можно запускать вручную через `workflow_dispatch`

## Что уже сделано
- Починены конфликты зависимостей (`supabase`/`httpx`) для стабильного CI запуска
- Добавлен `force_remote=True` для remote-only источников (`remotive`, `jobscollider`, `jobicy`)
- Добавлена нормализация текста для румынских диакритик в remote-фильтре
- Улучшена диагностика источников в логах GitHub Actions
- Добавлена выгрузка вакансий в Google Sheets
  - Дедупликация по `url` относительно уже существующих строк в Google Sheet
  - Добавлены поля `salary` (число или диапазон) и `short_description_ru` (краткое описание на русском с эмодзи)
  - Автоматическая вставка заголовков в первую строку, если лист был без шапки

## Google Sheets интеграция
Используются секреты GitHub Actions:
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`

Запись идет в первый лист документа (`sheet1`).

