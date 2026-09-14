# gym-tracker — трекер питания (MVP)

Трекер прогресса в зале + питание с прогнозом. На этом этапе реализован **модуль питания**:
итоговые БЖУ за день присылаются в Telegram-бота (значения берёшь из Yazio), бот пишет их в
БД, а API отдаёт агрегацию и сравнение с нормой.

## Как это работает

```
Yazio (телефон) ──«Б150 Ж80 У200 К2100»──▶ Telegram-бот (long polling)
                                               │  парсер → БЖУ
                                               ▼
                                           PostgreSQL / SQLite
                                               │
                                               ▼
                                       FastAPI: агрегация, норма, динамика
```

Три части:
1. **Бот** (`app/bot.py`) — принимает сообщение, парсит, пишет в БД. Работает напрямую по
   Telegram Bot API через `aiohttp` (без aiogram — меньше зависимостей, видно протокол).
2. **Сервисный слой** (`app/nutrition.py`) — апсерт записи за день, агрегация за N дней,
   нормы.
3. **API** (`app/api.py`) — REST-эндпоинты для отчётов и альтернативного ввода.

Ключевые решения:
- **Апсерт, не INSERT** — на `(user_id, day)` уникальное ограничение, повторная отправка за
  день перезаписывает (не дублирует).
- **Часовой пояс** — «день» считается по `Europe/Moscow`, не по серверному UTC.
- **Норма отдельно от факта** — `goals` хранит целевые БЖУ/ккал, сравнение — это JOIN.
- **async сетевой слой + sync SQLAlchemy** — бот/API на asyncio, БД-вызовы через
  `asyncio.to_thread` (переход на asyncpg = смена драйвера, логика не меняется).

## Соответствие стека файлам

| Технология | Где |
|---|---|
| asyncio / aiohttp | `app/bot.py` (long polling, `poll_loop`, `run_db`) |
| FastAPI | `app/api.py` |
| SQLAlchemy (ORM, апсерт) | `app/models.py`, `app/nutrition.py` |
| PostgreSQL (prod) / SQLite (dev) | `app/db.py`, `docker-compose.yml` |
| Парсер БЖУ (regex + валидация) | `app/parser.py` |
| Конфиг из env | `app/config.py` (pydantic-settings) |
| Тесты | `tests/` (unittest) |
| Docker | `Dockerfile`, `docker-compose.yml` |

## Запуск (локально, SQLite)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# .env
cp .env.example .env   # впиши BOT_TOKEN из @BotFather

# тесты
python -m unittest discover -s tests -t .

# API
python run_api.py                      # http://127.0.0.1:8000
# или: uvicorn app.api:app --port 8000

# бот
python run_bot.py
```

## Запуск (Docker, PostgreSQL)

```bash
export BOT_TOKEN=...          # или лежит в .env
docker compose up --build     # api на :8000, bot в polling, postgres рядом
```

## API

- `GET  /health` — живость сервиса
- `POST /api/nutrition` — `{tg_id, protein, fat, carbs, calories, day?}` — запись за день
- `GET  /api/summary/{tg_id}?days=7` — агрегация + сравнение с нормой
- `POST /api/goals` — `{tg_id, protein, fat, carbs, calories}` — задать норму
- `GET  /api/day/{tg_id}?day=YYYY-MM-DD` — запись за конкретный день

## Форматы сообщения боту

```
Б150 Ж80 У200 К2100
150 80 200 2100
150/80/200/2100
```
(порядок: белки → жиры → углеводы → калории)

## Что дальше (roadmap)

- Модуль тела: вес, % жира, замеры (`body_measurements`).
- Модуль силовых: `exercises`, `strength_log` + динамика в расчётном 1ПМ.
- Модуль прогноза: оценка 1ПМ + темп по скользящему окну + доверительный интервал.
- Графики динамики (frontend).
- Миграции через Alembic вместо `create_all`.
