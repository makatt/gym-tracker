# gym-tracker — трекер зала и питания

Трекер прогресса в зале + питание с прогнозом. Реализовано два модуля:

1. **Питание** — итоговые БЖУ за день (из Yazio) присылаются боту, агрегация за
   неделю/месяц, сравнение с нормой.
2. **Силовые** — подходы «упражнение × вес × повторы», история по упражнению и динамика
   в расчётном 1ПМ (одноповторном максимуме).

## Как это работает

```
Yazio (телефон) ──«Б150 Ж80 У200 К2100»──▶ Telegram-бот (aiogram, long polling)
зал            ──«жим 80x2»─────────────▶      │
                                               │  парсер → запись в БД
                                               ▼
                                           PostgreSQL / SQLite
                                               │
                                               ▼
                              FastAPI: агрегация, норма, динамика, 1ПМ
```

Три слоя:
- **Бот** (`app/bot.py`) — aiogram 3.x, long polling. Принимает БЖУ и силовые подходы,
  парсит, пишет в БД, отдаёт отчёты.
- **Сервисный слой** — `app/nutrition.py` (апсерт БЖУ, агрегация, нормы) и
  `app/strength.py` (упражнения, подходы, расчётный 1ПМ, динамика).
- **API** (`app/api.py`) — REST для отчётов и альтернативного ввода.

Ключевые решения:
- **Апсерт, не INSERT** — на `(user_id, day)` уникальное ограничение, повторная отправка
  БЖУ за день перезаписывает.
- **1ПМ по формуле Эпли** — `вес × (1 + повторы/30)`, чтобы сравнивать подходы с разным
  числом повторов («80×2» vs «90×1»). Без этого динамику по весу считать нельзя.
- **Часовой пояс** — «день» считается по `Europe/Moscow`, не по серверному UTC.
- **Норма отдельно от факта** — `goals` хранит целевые БЖУ, сравнение — это JOIN.
- **async сетевой слой + sync SQLAlchemy** — aiogram/FastAPI на asyncio, БД-вызовы через
  `asyncio.to_thread` (переход на asyncpg = смена драйвера, логика не меняется).

## Соответствие стека файлам

| Технология | Где |
|---|---|
| asyncio / aiogram | `app/bot.py` (long polling, роутер, `run_db`) |
| FastAPI | `app/api.py` |
| SQLAlchemy (ORM, апсерт) | `app/models.py`, `app/nutrition.py`, `app/strength.py` |
| Расчёт 1ПМ (Epley) | `app/strength.py` (`estimate_1rm`) |
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

# .env
cp .env.example .env   # впиши BOT_TOKEN из @BotFather

# тесты
python -m unittest discover -s tests -t .

# API
python run_api.py                      # http://127.0.0.1:8000

# бот
python run_bot.py
```

## Запуск (Docker, PostgreSQL)

```bash
export BOT_TOKEN=...
docker compose up --build     # api на :8000, bot в polling, postgres рядом
```

## API

Питание:
- `POST /api/nutrition` — `{tg_id, protein, fat, carbs, calories, day?}`
- `GET  /api/summary/{tg_id}?days=7` — агрегация + сравнение с нормой
- `POST /api/goals` — `{tg_id, protein, fat, carbs, calories}`
- `GET  /api/day/{tg_id}?day=YYYY-MM-DD`

Силовые:
- `POST /api/strength` — `{tg_id, exercise, weight, reps, day?}`
- `GET  /api/exercises/{tg_id}` — список упражнений
- `GET  /api/strength/{tg_id}/{exercise}` — история подходов
- `GET  /api/strength/progress/{tg_id}/{exercise}` — динамика 1ПМ (старт/лучший/прирост)

## Форматы сообщений боту

Питание (порядок: белки → жиры → углеводы → калории):
```
Б150 Ж80 У200 К2100
150 80 200 2100
```

Силовые (упражнение → вес × повторы):
```
жим 80x2
/log присед 100x5
```

Команды: `/week`, `/month`, `/today`, `/setgoal`, `/goal`, `/strength <упр>`, `/exercises`.

## Что дальше (roadmap)

- Модуль тела: вес, % жира, замеры (`body_measurements`).
- Модуль прогноза: темп роста 1ПМ по скользящему окну + оценка срока до целевого веса
  («когда будет 100 кг») с доверительным интервалом.
- Графики динамики (frontend).
- Миграции через Alembic вместо `create_all`.
