"""Telegram-бот на aiogram 3.x — питание, силовые и тренировки.

Тренировка: /workout [день] [дата] → бот показывает упражнения шаблона с прошлыми
результатами; подходы пишутся списком в активную тренировку; /done — сводка.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import nutrition as svc
from app import strength as strength_svc
from app import workout as workout_svc
from app.config import settings
from app.db import SessionLocal, init_db
from app.parser import ParseError, parse_macros, parse_strength_batch

log = logging.getLogger("gym.bot")

bot = Bot(token=settings.bot_token)
dp = Dispatcher()
router = Router()

HELP = (
    "📊 <b>Трекер зала и питания</b>\n\n"
    "<b>Тренировка</b>:\n"
    "/workout — начать (кнопки дней: спина/грудь/руки)\n"
    "/workout спина 2026-09-14 — день + дата (без даты = сегодня)\n"
    "/done — закончить и показать сводку с изменениями\n"
    "/workouts — история тренировок\n\n"
    "<b>Силовые</b> — подходы одной строкой (пишутся в активную тренировку):\n"
    "<code>жим 80x2, присед 100x5</code>\n"
    "<b>Питание</b> — итог дня:\n"
    "<code>Б150 Ж80 У200 К2100</code>\n"
    "/week · /month · /setgoal Б.. Ж.. У.. К.."
)


def _run_db(fn, *args, **kwargs):
    with SessionLocal() as session:
        return fn(session, *args, **kwargs)


async def run_db(fn, *args, **kwargs):
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


def _fmt_workout_report(r: dict) -> str:
    lines = [f"🏁 Тренировка: {r['name'] or '—'} ({r['day']})"]
    if not r["exercises"]:
        lines.append("Подходов не записано.")
        return "\n".join(lines)
    for name, e in r["exercises"].items():
        cur, prev, d = e["current"], e["previous"], e["delta_e1rm"]
        line = f"• {name}: {cur['weight']:g}×{cur['reps']}"
        if prev is not None:
            arrow = "↑" if d > 0 else ("↓" if d < 0 else "=")
            line += f" | прошлый {prev['weight']:g}×{prev['reps']} → 1ПМ {arrow}{abs(d):g}"
        lines.append(line)
    return "\n".join(lines)


def _suggest_kb(name: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Повторить", callback_data=f"repeat:{name}")
    kb.button(text="✏️ Изменить", callback_data=f"edit:{name}")
    return kb


# ---------- тренировки ----------

async def _workout_intro_text(user_id: int, workout, template: dict) -> str:
    lines = [f"🏋️ <b>Тренировка: {workout.name}</b> ({workout.day})", "Упражнения (прошлый раз):"]
    for ex in template["exercises"]:
        prev = await run_db(workout_svc.previous_entry, user_id, ex)
        if prev:
            lines.append(f"• {ex} — {prev['weight']:g}×{prev['reps']}")
        else:
            lines.append(f"• {ex} — (нет записей)")
    lines.append("\nПришли подходы списком: <code>подтягивания 70x5, тяга 60x8</code>")
    lines.append("Закончил — /done")
    return "\n".join(lines)


@router.message(Command("workout"))
async def cmd_workout(msg: Message) -> None:
    user = await _user(msg)
    templates = await run_db(workout_svc.list_templates, user.id)

    parts = (msg.text or "").split(maxsplit=1)
    rest = (parts[1] if len(parts) > 1 else "").strip()
    m_date = re.search(r"\d{4}-\d{2}-\d{2}", rest)
    day = date.fromisoformat(m_date.group()) if m_date else None
    name_arg = re.sub(r"\d{4}-\d{2}-\d{2}", "", rest).strip().lower()

    if name_arg:
        matched = [t for t in templates
                   if t["name"].lower() == name_arg or t["name"].lower().startswith(name_arg)]
        if not matched:
            await msg.answer(
                f"Шаблон «{name_arg}» не найден. Доступно: "
                + ", ".join(t["name"] for t in templates))
            return
        w = await run_db(workout_svc.create_workout, user.id, matched[0]["name"], day)
        await msg.answer(await _workout_intro_text(user.id, w, matched[0]),
                         parse_mode=ParseMode.HTML)
        return

    kb = InlineKeyboardBuilder()
    for t in templates:
        cb = f"wk:{t['name']}"
        if day:
            cb += f":{day.isoformat()}"
        kb.button(text=t["name"], callback_data=cb)
    kb.adjust(1)
    await msg.answer("Какой день тренировки?" + (f"\n(дата: {day})" if day else ""),
                     reply_markup=kb.as_markup())


@router.message(Command("done"))
async def cmd_done(msg: Message) -> None:
    user = await _user(msg)
    report = await run_db(workout_svc.finish_workout, user.id)
    if report is None:
        await msg.answer("Нет активной тренировки. Начни: /workout")
        return
    await msg.answer(_fmt_workout_report(report))


@router.message(Command("workouts"))
async def cmd_workouts(msg: Message) -> None:
    user = await _user(msg)
    ws = await run_db(workout_svc.list_workouts, user.id)
    if not ws:
        await msg.answer("Тренировок пока нет. /workout")
        return
    lines = ["История тренировок:"]
    for w in ws:
        flag = " 🟢 (активна)" if w["active"] else ""
        lines.append(f"• {w['day']} {w['name'] or '—'} — {w['count']} подх.{flag}")
    await msg.answer("\n".join(lines))


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


# ---------- inline-кнопки ----------

@router.callback_query()
async def on_callback(cb: CallbackQuery) -> None:
    data = cb.data or ""
    if not cb.message:
        return
    user = await run_db(svc.ensure_user, cb.from_user.id, cb.from_user.username)

    if data.startswith("wk:"):
        parts = data.split(":")
        name = parts[1]
        day = date.fromisoformat(parts[2]) if len(parts) > 2 else None
        w = await run_db(workout_svc.create_workout, user.id, name, day)
        templates = await run_db(workout_svc.list_templates, user.id)
        template = next((t for t in templates if t["name"] == name), {"exercises": []})
        text = await _workout_intro_text(user.id, w, template)
        await cb.message.edit_text(text, parse_mode=ParseMode.HTML)
        await cb.answer()

    elif data.startswith("repeat:"):
        name = data.split(":", 1)[1]
        last = await run_db(strength_svc.last_entry, user.id, name)
        if last is None:
            await cb.answer("Нет прошлых подходов", show_alert=True)
            return
        # в активную тренировку, если есть
        if await run_db(workout_svc.active_workout, user.id):
            await run_db(workout_svc.log_to_workout, user.id, name, last["weight"], last["reps"])
        else:
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

    # 1. Силовые (один или несколько подходов).
    if "x" in low or "х" in low:
        try:
            entries = parse_strength_batch(text)
        except ParseError as e:
            await msg.answer(f"⚠️ {e}")
            return
        user = await _user(msg)
        active = await run_db(workout_svc.active_workout, user.id)
        for e in entries:
            if active is not None:
                await run_db(workout_svc.log_to_workout, user.id, e.exercise, e.weight, e.reps)
            else:
                await run_db(strength_svc.log_strength, user.id, e.exercise, e.weight, e.reps)
        prefix = "✅ В тренировку:\n" if active is not None else "✅ Записано:\n"
        await msg.answer(prefix + "\n".join(_fmt_entry(e) for e in entries))
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
        last = await run_db(strength_svc.last_entry, user.id, name)
        if last is None:
            await msg.answer(f"Нет записей по «{name}». Пришли: {name} 80x2")
            return
        await msg.answer(
            f"«{name}»: в прошлый раз {last['weight']:g}×{last['reps']} "
            f"(1ПМ ~{last['e1rm']:g}). Повторить?",
            reply_markup=_suggest_kb(name).as_markup(),
        )
        return

    # 4. Непонятно.
    await msg.answer(
        "Не понял. Форматы:\n"
        "• силовая: <code>жим 80x2</code> (или списком через запятую)\n"
        "• питание: <code>Б150 Ж80 У200 К2100</code>\n"
        "• тренировка: /workout\n"
        "/help — все команды",
        parse_mode=ParseMode.HTML,
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    dp.include_router(router)
    log.info("Бот запущен (aiogram), long polling…")
    await dp.start_polling(bot)
