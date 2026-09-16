"""Сервис силовых: упражнения, логи подходов, расчётный 1ПМ, динамика."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.timeutil import today


def estimate_1rm(weight: float, reps: int) -> float:
    """Расчётный одноповторный максимум по формуле Эпли: вес × (1 + повторы/30).

    Нужен, чтобы сравнивать подходы с разным числом повторов
    («80×2» vs «90×1») — иначе динамику по «весу» считать нельзя.
    """
    if reps <= 1:
        return round(weight, 1)
    return round(weight * (1 + reps / 30.0), 1)


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def ensure_exercise(session: Session, user_id: int, name: str) -> models.Exercise:
    name = _normalize(name)
    ex = session.scalar(
        select(models.Exercise).where(
            models.Exercise.user_id == user_id,
            models.Exercise.name == name,
        )
    )
    if ex is None:
        ex = models.Exercise(user_id=user_id, name=name)
        session.add(ex)
        session.flush()
    return ex


def log_strength(
    session: Session,
    user_id: int,
    name: str,
    weight: float,
    reps: int,
    day: date | None = None,
) -> models.StrengthLog:
    ex = ensure_exercise(session, user_id, name)
    entry = models.StrengthLog(
        user_id=user_id,
        exercise_id=ex.id,
        day=day or today(),
        weight=weight,
        reps=reps,
    )
    session.add(entry)
    session.commit()
    return entry


def list_exercises(session: Session, user_id: int) -> list[str]:
    rows = session.scalars(
        select(models.Exercise.name)
        .where(models.Exercise.user_id == user_id)
        .order_by(models.Exercise.name)
    ).all()
    return list(rows)


def history(session: Session, user_id: int, name: str) -> list[dict]:
    """Все подходы по упражнению, отсортированные по дате (с расчётным 1ПМ)."""
    ex = session.scalar(
        select(models.Exercise).where(
            models.Exercise.user_id == user_id,
            models.Exercise.name == _normalize(name),
        )
    )
    if ex is None:
        return []
    rows = session.scalars(
        select(models.StrengthLog)
        .where(models.StrengthLog.exercise_id == ex.id)
        .order_by(models.StrengthLog.day, models.StrengthLog.id)
    ).all()
    return [
        {
            "day": r.day.isoformat(),
            "weight": r.weight,
            "reps": r.reps,
            "e1rm": estimate_1rm(r.weight, r.reps),
        }
        for r in rows
    ]


def progress(session: Session, user_id: int, name: str) -> dict:
    """Сводка динамики: первый/лучший подход и прирост расчётного 1ПМ."""
    h = history(session, user_id, name)
    if not h:
        return {"exercise": _normalize(name), "records": 0, "history": []}

    best = max(h, key=lambda r: r["e1rm"])
    first = h[0]
    return {
        "exercise": _normalize(name),
        "records": len(h),
        "first": first,
        "best": best,
        "first_e1rm": first["e1rm"],
        "best_e1rm": best["e1rm"],
        "delta_e1rm": round(best["e1rm"] - first["e1rm"], 1),
        "history": h,
    }


def last_entry(session: Session, user_id: int, name: str) -> dict | None:
    """Последний (самый свежий) подход по упражнению."""
    h = history(session, user_id, name)
    return h[-1] if h else None
