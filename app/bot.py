"""Telegram-бот на aiogram 3.x — питание (БЖУ) + силовые (подходы).

Быстрый ввод силовых:
- списком: «жим 80x2, присед 100x5»
- автоподстановка: напиши «жим» → предложит повторить прошлый подход
- кнопками: /trening → топ упражнений
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import nutrition as svc
from app import strength as strength_svc
from app.config import settings
from app.db import SessionLocal, init_db
from app.parser import ParseError, parse_macros, parse_strength_batch

log = logging.getLogger("gym.bot")

bot = Bot(token=settings.bot_token)
dp = Dispatcher()
router = Router()

HELP = (
    "📊 <b>Трекер зала и питания</b>\n\n"
    "<b>Питание</b> — итог дня из Yazio:\n"
    "<code>Б150 Ж80 У200 К2100</code> или <code>150 80 200 2100</code>\n"
    "/week · /month · /today · /setgoal Б.. Ж.. У.. К.. · /goal\n\n"
    "<b>Силовые</b> — подходы одной строкой (или списком):\n"
    "<code>жим 80x2</code> · <code>жим 80x2, присед 100x5</code>\n"
    "Напиши только <code>жим</code> — предложу повторить прошлый подход.\n"
    "/strength жим — динамика · /trening — топ упражнений · /exercises — все"
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


def _fmt_entry(e) -> str:
    return f"• {e.exercise}: {e.weight:g}×{e.reps} (1ПМ ~{strength_svc.estimate_1rm(e.weight, e.reps):g})"


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


def _fmt_progress(p: dict) -> str:
    if p["records"] == 0:
        return f"Нет записей по «{p['exercise']}». Добавь: {p['exercise']} 80x2"
    b, f = p["best"], p["first"]
    return "\n".join([
        f"🏋️ <b>{p['exercise']}</b> — записей: {p['records']}",
        f"Старт: {f['weight']:g}×{f['reps']} → 1ПМ ~{f['e1rm']:g}",
        f"Лучший: {b['weight']:g}×{b['reps']} → 1ПМ ~{b['e1rm']:g}",
        f"Прирост 1ПМ: {'+' if p['delta_e1rm'] >= 0 else ''}{p['delta_e1rm']:g} кг",
    ])


def _suggest_kb(name: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Повторить", callback_data=f"repeat:{name}")
    kb.button(text="✏️ Изменить", callback_data=f"edit:{name}")
    return kb


async def _suggest_last(msg: Message, user_id: int, name: str) -> None:
    last = await run_db(strength_svc.last_entry, user_id, name)
    if last is None:
        await msg.answer(f"Нет записей по «{name}». Пришли: {name} 80x2")
        return
    await msg.answer(
        f"«{name}»: в прошлый раз {last['weight']:g}×{last['reps']} "
        f"(1ПМ ~{last['e1rm']:g}). Повторить?",
        reply_markup=_suggest_kb(name).as_markup(),
    )


# ---------- питание ----------

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
    parts = (msg.text or "").split(maxsplit=1)
    args = parts[1] if len(parts) > 1 else ""
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


# ---------- силовые ----------

@router.message(Command("log"))
async def cmd_log(msg: Message) -> None:
    parts = (msg.text or "").split(maxsplit=1)
    args = parts[1] if len(parts) > 1 else ""
    try:
        entries = parse_strength_batch(args)
    except ParseError as err:
        await msg.answer(f"⚠️ {err}")
        return
    user = await _user(msg)
    for e in entries:
        await run_db(strength_svc.log_strength, user.id, e.exercise, e.weight, e.reps)
    await msg.answer("✅ Записано:\n" + "\n".join(_fmt_entry(e) for e in entries))


@router.message(Command("strength"))
async def cmd_strength(msg: Message) -> None:
    parts = (msg.text or "").split(maxsplit=1)
    name = (parts[1] if len(parts) > 1 else "").strip()
    if not name:
        await msg.answer("Укажи упражнение: /strength жим\nСписок: /exercises")
        return
    user = await _user(msg)
    p = await run_db(strength_svc.progress, user.id, name)
    await msg.answer(_fmt_progress(p), parse_mode=ParseMode.HTML)


@router.message(Command("exercises"))
async def cmd_exercises(msg: Message) -> None:
    user = await _user(msg)
    names = await run_db(strength_svc.list_exercises, user.id)
    if not names:
        await msg.answer("Упражнений пока нет. Добавь: жим 80x2")
    else:
        await msg.answer("Твои упражнения:\n" + "\n".join(f"• {n}" for n in names))


@router.message(Command("trening"))
async def cmd_trening(msg: Message) -> None:
    user = await _user(msg)
    names = await run_db(strength_svc.list_exercises, user.id)
    if not names:
        await msg.answer("Упражнений пока нет. Добавь: жим 80x2")
        return
    kb = InlineKeyboardBuilder()
    for n in names[:10]:
        kb.button(text=n, callback_data=f"suggest:{n}")
    kb.adjust(2)
    await msg.answer("Выбери упражнение:", reply_markup=kb.as_markup())


# ---------- inline-кнопки (повторить / изменить / выбрать) ----------

@router.callback_query()
async def on_callback(cb: CallbackQuery) -> None:
    data = cb.data or ""
    if not cb.message:
        return
    user = await run_db(svc.ensure_user, cb.from_user.id, cb.from_user.username)

    if data.startswith("repeat:"):
        name = data.split(":", 1)[1]
        last = await run_db(strength_svc.last_entry, user.id, name)
        if last is None:
            await cb.answer("Нет прошлых подходов", show_alert=True)
            return
        await run_db(strength_svc.log_strength, user.id, name, last["weight"], last["reps"])
        await cb.message.edit_text(f"✅ {name}: {last['weight']:g}×{last['reps']} записан")
        await cb.answer("Записано")

    elif data.startswith("edit:"):
        name = data.split(":", 1)[1]
        await cb.message.edit_text(f"Пришли новый подход: <code>{name} 80x2</code>",
                                   parse_mode=ParseMode.HTML)
        await cb.answer()

    elif data.startswith("suggest:"):
        name = data.split(":", 1)[1]
        last = await run_db(strength_svc.last_entry, user.id, name)
        if last is None:
            await cb.answer(f"Нет записей по «{name}»", show_alert=True)
            return
        await cb.message.edit_text(
            f"«{name}»: в прошлый раз {last['weight']:g}×{last['reps']} "
            f"(1ПМ ~{last['e1rm']:g}). Повторить?",
            reply_markup=_suggest_kb(name).as_markup(),
        )
        await cb.answer()

    else:
        await cb.answer()


# ---------- авто-детект ----------

@router.message(F.text)
async def on_text(msg: Message) -> None:
    text = msg.text or ""
    low = text.lower()

    # 1. Силовые (один или несколько подходов) — есть «x/х».
    if "x" in low or "х" in low:
        try:
            entries = parse_strength_batch(text)
        except ParseError as e:
            await msg.answer(f"⚠️ {e}")
            return
        user = await _user(msg)
        for e in entries:
            await run_db(strength_svc.log_strength, user.id, e.exercise, e.weight, e.reps)
        await msg.answer("✅ Записано:\n" + "\n".join(_fmt_entry(e) for e in entries))
        return

    # 2. БЖУ.
    try:
        m = parse_macros(text)
    except ParseError:
        m = None
    if m is not None:
        user = await _user(msg)
        await run_db(svc.upsert_day, user.id, svc.today(), m)
        await msg.answer(f"✅ Записал {svc.today()}: {_fmt_macros(m.protein, m.fat, m.carbs, m.calories)}")
        return

    # 3. Имя упражнения → автоподстановка прошлого подхода.
    name = " ".join(text.strip().lower().split())
    user = await _user(msg)
    if name and name in await run_db(strength_svc.list_exercises, user.id):
        await _suggest_last(msg, user.id, name)
        return

    # 4. Непонятно.
    await msg.answer(
        "Не понял. Форматы:\n"
        "• силовая: <code>жим 80x2</code> (или списком через запятую)\n"
        "• питание: <code>Б150 Ж80 У200 К2100</code>\n"
        "/help — все команды",
        parse_mode=ParseMode.HTML,
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    dp.include_router(router)
    log.info("Бот запущен (aiogram), long polling…")
    await dp.start_polling(bot)
