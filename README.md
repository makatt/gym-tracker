# gym-tracker — трекер зала и питания

Трекер прогресса в зале + питание. Три модуля:

1. **Тренировки** — шаблоны дней (спина/грудь/руки), активная тренировка с датой,
   прошлые результаты по каждому упражнению, сводка с изменением 1ПМ.
2. **Силовые** — подходы «упражнение × вес × повторы», история и динамика в расчётном 1ПМ.
3. **Питание** — итоговые БЖУ за день (из Yazio), агрегация за неделю/месяц, сравнение с нормой.

## Как это работает

```
Yazio (телефон) ──«Б150 Ж80 У200 К2100»──▶ Telegram-бот (aiogram, long polling)
зал            ──«жим 80x2, присед 100x5»─▶      │
зал            ──/workout спина────────────▶      │
                                                  │  парсер → запись в БД
                                                  ▼
                                           PostgreSQL / SQLite
                                                  │
                                                  ▼
                              FastAPI: агрегация, норма, динамика, тренировки
```

Слои:
- **Бот** (`app/bot.py`) — aiogram 3.x: тренировки, силовые, питание, inline-кнопки.
- **Сервисы** — `app/nutrition.py`, `app/strength.py`, `app/workout.py` (шаблоны, активная
  тренировка, сравнение с прошлым).
- **API** (`app/api.py`) — REST для отчётов и альтернативного ввода.

Ключевые решения:
- **Апсерт, не INSERT** — БЖУ за день и подход в тренировке перезаписываются при повторе.
- **1ПМ по формуле Эпли** — `вес × (1 + повторы/30)`, чтобы сравнивать подходы с разным
  числом повторов. Динамика и «изменение vs прошлый раз» считаются по 1ПМ.
- **Тренировка** — активный `Workout` на пользователя; подходы пишутся в него; `/done`
  закрывает и показывает сводку (текущий vs прошлый, ↑/↓ 1ПМ).
- **Шаблоны** — `workout_templates` + `template_exercises`; стартовые дни (спина/грудь/руки)
  в `app/templates.py`, разворачиваются при первом входе.
- **Часовой пояс** — «день» считается по `Europe/Moscow`.
- **async сетевой слой + sync SQLAlchemy** — БД-вызовы через `asyncio.to_thread`.

## Соответствие стека файлам

| Технология | Где |
|---|---|
| asyncio / aiogram | `app/bot.py` (long polling, роутер, inline-кнопки) |
| FastAPI | `app/api.py` |
| SQLAlchemy (ORM, апсерт) | `app/models.py`, `app/nutrition.py`, `app/strength.py`, `app/workout.py` |
| Расчёт 1ПМ (Epley) | `app/strength.py` (`estimate_1rm`) |
| Шаблоны тренировок | `app/templates.py`, `app/workout.py` |
| PostgreSQL (prod) / SQLite (dev) | `app/db.py`, `docker-compose.yml` |
| Парсеры (БЖУ + силовые) | `app/parser.py` |
| Конфиг из env | `app/config.py` (pydantic-settings) |
| Часовой пояс (MSK) | `app/timeutil.py` |
| Тесты | `tests/` (unittest) |
| Docker | `Dockerfile`, `docker-compose.yml` |

## Запуск (локально, SQLite)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # впиши BOT_TOKEN из @BotFather

python -m unittest discover -s tests -t .   # тесты
python run_api.py                           # API http://127.0.0.1:8000
python run_bot.py                           # бот
```

## Запуск (Docker, PostgreSQL)

```bash
export BOT_TOKEN=...
docker compose up --build
```

## API

Питание: `POST /api/nutrition`, `GET /api/summary/{tg_id}?days=7`, `POST /api/goals`,
`GET /api/day/{tg_id}`.
Силовые: `POST /api/strength`, `GET /api/exercises/{tg_id}`, `GET /api/strength/{tg_id}/{exercise}`,
`GET /api/strength/progress/{tg_id}/{exercise}`.
Тренировки: `POST /api/workout`, `POST /api/workout/log`, `POST /api/workout/done`,
`GET /api/workouts/{tg_id}`.

## Форматы сообщений боту

Тренировка:
```
/workout                 — выбор дня кнопками
/workout спина 2026-09-14 — день + дата (без даты = сегодня)
→ упражнения кнопками (с прошлым результатом) → нажал → пришли «70x5»
/done (или 🏁)           — сводка с изменениями vs прошлый раз
/workouts                — история тренировок
```

Силовые (пишутся в активную тренировку, если она начата):
```
жим 80x2
жим 80x2, присед 100x5, тяга 120x3
жим                      — предложит повторить прошлый подход
```

Питание (порядок: белки → жиры → углеводы → калории):
```
Б150 Ж80 У200 К2100
```

## Что дальше (roadmap)

- Модуль тела: вес, % жира, замеры (`body_measurements`).
- Модуль прогноза: темп роста 1ПМ по скользящему окну + оценка срока до целевого веса.
- Редактирование шаблонов тренировок через бота.
- Графики динамики (frontend), миграции через Alembic.
