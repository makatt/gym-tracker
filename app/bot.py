"""Telegram-бот (long polling) — приём итоговых БЖУ за день и отчёты.

Работает напрямую по Telegram Bot API через aiohttp (без aiogram): так код
не тянет лишних зависимостей и видно, как устроен протокол под капотом.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from app import nutrition as svc
from app.config import settings
from app.db import SessionLocal, init_db
from app.parser import ParseError, parse_macros

log = logging.getLogger("gym.bot")

API = f"https://api.telegram.org/bot{settings.bot_token}"

HELP = (
    "📊 <b>Трекер питания</b>\n\n"
    "Пришли итог дня из Yazio одним сообщением:\n"
    "<code>Б150 Ж80 У200 К2100</code>\n"
    "или <code>150 80 200 2100</code>\n"
    "(порядок: белки → жиры → углеводы → калории)\n\n"
    "Команды:\n"
    "/today — сегодняшний день\n"
    "/week — неделя (среднее vs норма)\n"
    "/month — месяц (среднее vs норма)\n"
    "/setgoal Б170 Ж90 У250 К2600 — задать норму\n"
    "/goal — показать текущую норму"
)


def _run_db(fn, *args, **kwargs):
    """Синхронная БД-операция в отдельной сессии (выполняется в потоке)."""
    with SessionLocal() as session:
        return fn(session, *args, **kwargs)


async def run_db(fn, *args, **kwargs):
    """Обёртка: sync SQLAlchemy в потоке, чтобы не блокировать event loop."""
    return await asyncio.to_thread(_run_db, fn, *args, **kwargs)


async def api_call(session: aiohttp.ClientSession, method: str, **params) -> dict:
    url = f"{API}/{method}"
    async with session.post(url, json=params, timeout=aiohttp.ClientTimeout(20)) as resp:
        return await resp.json()


async def send_message(session: aiohttp.ClientSession, chat_id: int, text: str) -> None:
    await api_call(session, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")


def _fmt_macros(p, f, c, kcal) -> str:
    return f"Б {p:g} · Ж {f:g} · У {c:g} · {kcal:g} ккал"


def _fmt_summary(s: dict) -> str:
    avg, goal, diff = s["daily_avg"], s["goal"], s["diff_vs_goal"]
    lines = [
        f"📈 За {s['period_days']} дн. (записей: {s['days_recorded']})",
        f"Среднее в день: {_fmt_macros(avg['protein'], avg['fat'], avg['carbs'], avg['calories'])}",
    ]
    if goal:
        lines.append(
            f"Норма: {_fmt_macros(goal['protein'], goal['fat'], goal['carbs'], goal['calories'])}"
        )
        lines.append(
            f"Отклонение: {_fmt_macros(diff['protein'], diff['fat'], diff['carbs'], diff['calories'])}"
        )
    else:
        lines.append("Норма не задана — /setgoal Б.. Ж.. У.. К..")
    return "\n".join(lines)


async def process_update(session: aiohttp.ClientSession, update: dict) -> None:
    """Обрабатывает одно сообщение из getUpdates."""
    msg = update.get("message")
    if not msg or "text" not in msg:
        return

    chat_id = msg["chat"]["id"]
    tg_id = msg.get("from", {}).get("id")
    username = msg.get("from", {}).get("username")
    text = msg["text"].strip()
    low = text.lower()

    if tg_id is None:
        return

    if low in ("/start", "/help"):
        reply = HELP
    elif low.startswith("/setgoal"):
        try:
            m = parse_macros(text[len("/setgoal"):].strip())
        except ParseError as e:
            reply = f"⚠️ Не понял норму. {e}"
        else:
            user = await run_db(svc.ensure_user, tg_id, username)
            await run_db(svc.set_goal, user.id, m)
            reply = f"✅ Норма: {_fmt_macros(m.protein, m.fat, m.carbs, m.calories)}"
    elif low == "/goal":
        user = await run_db(svc.ensure_user, tg_id, username)
        goal = await run_db(svc.get_goal, user.id)
        if goal is None:
            reply = "Норма не задана. /setgoal Б.. Ж.. У.. К.."
        else:
            reply = f"🎯 Норма: {_fmt_macros(goal.protein, goal.fat, goal.carbs, goal.calories)}"
    elif low in ("/today", "/week", "/month"):
        user = await run_db(svc.ensure_user, tg_id, username)
        if low == "/today":
            day = await run_db(svc.get_day, user.id, svc.today())
            reply = (f"Сегодня: {_fmt_macros(day.protein, day.fat, day.carbs, day.calories)}"
                     if day else "Сегодня ещё нет записи. Пришли БЖУ.")
        else:
            days = 7 if low == "/week" else 30
            reply = _fmt_summary(await run_db(svc.summary, user.id, days))
    else:
        try:
            m = parse_macros(text)
        except ParseError as e:
            reply = f"⚠️ {e}"
        else:
            user = await run_db(svc.ensure_user, tg_id, username)
            await run_db(svc.upsert_day, user.id, svc.today(), m)
            reply = f"✅ Записал {svc.today()}: {_fmt_macros(m.protein, m.fat, m.carbs, m.calories)}"

    await send_message(session, chat_id, reply)


async def poll_loop() -> None:
    """Бесконечный long polling с обработкой смещения offset."""
    init_db()
    offset = 0
    async with aiohttp.ClientSession() as session:
        log.info("Бот запущен, long polling…")
        while True:
            try:
                data = await api_call(session, "getUpdates", offset=offset,
                                      timeout=settings.poll_timeout)
            except Exception as e:  # noqa: BLE001 — сеть мигает, ждём и пробуем снова
                log.warning("getUpdates error: %s", e)
                await asyncio.sleep(3)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                try:
                    await process_update(session, update)
                except Exception as e:  # noqa: BLE001 — не роняем весь цикл
                    log.exception("Ошибка обработки update: %s", e)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(poll_loop())
