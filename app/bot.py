"""Telegram-бот на aiogram 3.x — приём итоговых БЖУ за день и отчёты.

Логика та же, что была в aiohttp-версии: парсинг → апсерт в БД → отчёты.
БД-вызовы (sync SQLAlchemy) выполняются через asyncio.to_thread, чтобы не
блокировать event loop aiogram.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app import nutrition as svc
from app.config import settings
from app.db import SessionLocal, init_db
from app.parser import ParseError, parse_macros

log = logging.getLogger("gym.bot")

bot = Bot(token=settings.bot_token)
dp = Dispatcher()
router = Router()

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


async def _user(msg: Message):
    return await run_db(svc.ensure_user, msg.from_user.id, msg.from_user.username)


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


@router.message(CommandStart())
async def cmd_start(msg: Message) -> None:
    await msg.answer(HELP, parse_mode=ParseMode.HTML)


@router.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    await msg.answer(HELP, parse_mode=ParseMode.HTML)


@router.message(Command("today"))
async def cmd_today(msg: Message) -> None:
    user = await _user(msg)
    day = await run_db(svc.get_day, user.id, svc.today())
    if day is None:
        await msg.answer("Сегодня ещё нет записи. Пришли БЖУ.")
    else:
        await msg.answer(f"Сегодня: {_fmt_macros(day.protein, day.fat, day.carbs, day.calories)}")


@router.message(Command("week"))
async def cmd_week(msg: Message) -> None:
    user = await _user(msg)
    await msg.answer(_fmt_summary(await run_db(svc.summary, user.id, 7)))


@router.message(Command("month"))
async def cmd_month(msg: Message) -> None:
    user = await _user(msg)
    await msg.answer(_fmt_summary(await run_db(svc.summary, user.id, 30)))


@router.message(Command("setgoal"))
async def cmd_setgoal(msg: Message) -> None:
    payload = (msg.text or "").split(maxsplit=1)
    args = payload[1] if len(payload) > 1 else ""
    try:
        m = parse_macros(args)
    except ParseError as e:
        await msg.answer(f"⚠️ Не понял норму. {e}")
        return
    user = await _user(msg)
    await run_db(svc.set_goal, user.id, m)
    await msg.answer(f"✅ Норма: {_fmt_macros(m.protein, m.fat, m.carbs, m.calories)}")


@router.message(Command("goal"))
async def cmd_goal(msg: Message) -> None:
    user = await _user(msg)
    goal = await run_db(svc.get_goal, user.id)
    if goal is None:
        await msg.answer("Норма не задана. /setgoal Б.. Ж.. У.. К..")
    else:
        await msg.answer(f"🎯 Норма: {_fmt_macros(goal.protein, goal.fat, goal.carbs, goal.calories)}")


@router.message(F.text)
async def on_text(msg: Message) -> None:
    try:
        m = parse_macros(msg.text)
    except ParseError as e:
        await msg.answer(f"⚠️ {e}")
        return
    user = await _user(msg)
    await run_db(svc.upsert_day, user.id, svc.today(), m)
    await msg.answer(
        f"✅ Записал {svc.today()}: {_fmt_macros(m.protein, m.fat, m.carbs, m.calories)}"
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    dp.include_router(router)
    log.info("Бот запущен (aiogram), long polling…")
    await dp.start_polling(bot)
