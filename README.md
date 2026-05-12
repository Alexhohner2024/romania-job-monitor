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
- IT + страховая сфера (не агент)
- Только релевантные гео-локации (Romania, Worldwide, Anywhere) для международных источников
- Исключает вакансии с требованием Advanced/Fluent English
- Автоматический перевод описания на русский через AI (Gemini Flash)

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
  - Улучшен парсинг `salary`: поддержка суффиксов `k`, валют ($, €, RON) и диапазонов
  - Реализован перевод `short_description_ru` через **Gemini API** (модель 1.5-flash)
  - Гео-фильтр: для глобальных сайтов (Remotive и др.) остаются только Worldwide/Romania вакансии
  - Автоматическая вставка заголовков в первую строку, если лист был без шапки

## Google Sheets интеграция
Используются секреты GitHub Actions:
- `GOOGLE_SHEET_ID`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GEMINI_API_KEY` (для перевода описаний)

Запись идет в первый лист документа (`sheet1`).

