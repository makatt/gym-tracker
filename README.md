# gym-tracker — трекер зала и питания

Трекер прогресса в зале + питание. Четыре модуля:

1. **Тело** — база (пол/рост/возраст/активность/цель), замеры (вес, % жира, мышцы),
   расчёт КБЖУ (BMR → TDEE → цель → БЖУ), динамика прогресса, фото-журнал.
2. **Тренировки** — шаблоны дней (спина/грудь/руки), активная тренировка с датой,
   упражнения кнопками с прошлыми результатами, сводка с изменением 1ПМ.
3. **Силовые** — подходы «упражнение × вес × повторы», история и динамика в расчётном 1ПМ.
4. **Питание** — итоговые БЖУ за день (из Yazio), агрегация за неделю/месяц, сравнение с нормой.

## Как это работает

```
Yazio (телефон) ──«Б150 Ж80 У200 К2100»──▶ Telegram-бот (aiogram, long polling)
зал            ──/workout спина · 70x5───▶      │
тело           ──/body 82 15 45───────────▶      │
                                                  │  парсер → запись в БД
                                                  ▼
                                           PostgreSQL / SQLite
                                                  │
                                                  ▼
                              FastAPI: КБЖУ, агрегация, динамика, тренировки
```

Слои:
- **Бот** (`app/bot.py`) — aiogram 3.x: тренировки, силовые, питание, тело, inline-кнопки, фото.
- **Сервисы** — `app/nutrition.py`, `app/strength.py`, `app/workout.py`, `app/body.py`.
- **API** (`app/api.py`) — REST для отчётов и альтернативного ввода.

Ключевые решения:
- **КБЖУ** — BMR (Миффлин–Сан Жеор) → TDEE × активность → цель (cut −20% / maintain / bulk +10%)
  → БЖУ (белки 2.0 г/кг, жиры 0.9 г/кг, углеводы — остаток).
- **1ПМ по формуле Эпли** — `вес × (1 + повторы/30)`; динамика и «изменение vs прошлый» по 1ПМ.
- **Апсерт, не INSERT** — БЖУ за день и подход в тренировке перезаписываются при повторе.
- **Тренировка** — активный `Workout` + `pending_exercise` (выбранное упражнение) → ввод
  «вес x повторы» без имени.
- **Шаблоны** — `workout_templates`; стартовые дни в `app/templates.py`.
- **Часовой пояс** — «день» по `Europe/Moscow`. **async + sync SQLAlchemy** через `asyncio.to_thread`.

## Соответствие стека файлам

| Технология | Где |
|---|---|
| asyncio / aiogram | `app/bot.py` |
| FastAPI | `app/api.py` |
| SQLAlchemy (ORM, апсерт) | `app/models.py`, `app/{nutrition,strength,workout,body}.py` |
| КБЖУ (BMR/TDEE/макросы) | `app/body.py` |
| Расчёт 1ПМ (Epley) | `app/strength.py` |
| Шаблоны тренировок | `app/templates.py`, `app/workout.py` |
| PostgreSQL (prod) / SQLite (dev) | `app/db.py`, `docker-compose.yml` |
| Парсеры | `app/parser.py` |
| Конфиг из env | `app/config.py` |
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

## Веб-дашборд

Открой `http://127.0.0.1:8000/` и введи свой Telegram ID вверху (сохраняется в браузере).
Тёмный read-only дашборд: обзор (вес, жир, цель, последняя тренировка + графики), тело
(КБЖУ, история замеров), силовые (динамика 1ПМ по упражнениям), тренировки, питание.
Графики — чистый SVG, без внешних CDN-зависимостей.

## API

Питание: `POST /api/nutrition`, `GET /api/summary/{tg_id}`, `POST /api/goals`, `GET /api/day/{tg_id}`.
Силовые: `POST /api/strength`, `GET /api/exercises/{tg_id}`, `GET /api/strength/{tg_id}/{exercise}`,
`GET /api/strength/progress/{tg_id}/{exercise}`.
Тренировки: `POST /api/workout`, `POST /api/workout/log`, `POST /api/workout/done`, `GET /api/workouts/{tg_id}`.
Тело: `POST /api/profile`, `POST /api/body`, `GET /api/kcal/{tg_id}`, `GET /api/body/progress/{tg_id}`.

## Форматы сообщений боту

Тело:
```
/setprofile м 180 2006 3 сушка   — пол, рост, год рождения, активность(1-5), цель
/body 82 15 45                   — вес, % жира, мышцы
/kcal                            — расчёт КБЖУ
/progress                        — динамика веса/жира
[фото]                           — сохраняется в журнал прогресса
```

Тренировка:
```
/workout                 — выбор дня кнопками
/workout спина 2026-09-14 — день + дата (без даты = сегодня)
→ упражнения кнопками → нажал → «70x5»
/done (или 🏁)           — сводка
```

Силовые (вне тренировки): `жим 80x2`, `жим 80x2, присед 100x5`.
Питание: `Б150 Ж80 У200 К2100`.

## Что дальше (roadmap)

- Модуль прогноза: темп роста 1ПМ по скользящему окну + оценка срока до целевого веса.
- Редактирование шаблонов тренировок через бота.
- Графики динамики (frontend), миграции через Alembic.
