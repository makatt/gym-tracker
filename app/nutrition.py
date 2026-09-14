"""Сервисный слой: пользователи, записи питания (апсерт), агрегация, нормы."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.db import engine
from app.parser import Macros


def today() -> date:
    """Сегодняшняя дата в часовом поясе приложения (MSK, а не серверный UTC)."""
    return datetime.now(ZoneInfo(settings.timezone)).date()


def ensure_user(session: Session, tg_id: int, username: str | None = None) -> models.User:
    """Возвращает пользователя по tg_id, создавая его при первом обращении."""
    user = session.scalar(select(models.User).where(models.User.tg_id == tg_id))
    if user is None:
        user = models.User(tg_id=tg_id, username=username)
        session.add(user)
        session.flush()
    return user


def upsert_day(session: Session, user_id: int, day: date, m: Macros) -> models.NutritionDay:
    """Вставляет или (при повторной отправке за тот же день) перезаписывает запись.

    UPSERT через диалект-специфичный INSERT … ON CONFLICT, чтобы одна строка
    на (user_id, day) гарантировалась на уровне БД, а не в коде.
    """
    values = dict(user_id=user_id, day=day, protein=m.protein, fat=m.fat,
                  carbs=m.carbs, calories=m.calories)

    if engine.dialect.name == "postgresql":
        stmt = pg_insert(models.NutritionDay).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_nutrition_user_day",
            set_={k: v for k, v in values.items() if k not in ("user_id", "day")},
        )
    else:
        stmt = sqlite_insert(models.NutritionDay).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "day"],
            set_={k: v for k, v in values.items() if k not in ("user_id", "day")},
        )

    session.execute(stmt)
    session.commit()
    return session.scalar(
        select(models.NutritionDay).where(
            models.NutritionDay.user_id == user_id,
            models.NutritionDay.day == day,
        )
    )


def get_day(session: Session, user_id: int, day: date) -> models.NutritionDay | None:
    return session.scalar(
        select(models.NutritionDay).where(
            models.NutritionDay.user_id == user_id,
            models.NutritionDay.day == day,
        )
    )


def set_goal(session: Session, user_id: int, m: Macros) -> models.Goal:
    goal = session.scalar(select(models.Goal).where(models.Goal.user_id == user_id))
    if goal is None:
        goal = models.Goal(user_id=user_id, protein=m.protein, fat=m.fat,
                           carbs=m.carbs, calories=m.calories)
        session.add(goal)
    else:
        goal.protein, goal.fat, goal.carbs, goal.calories = m.protein, m.fat, m.carbs, m.calories
    session.commit()
    return goal


def get_goal(session: Session, user_id: int) -> models.Goal | None:
    return session.scalar(select(models.Goal).where(models.Goal.user_id == user_id))


def summary(session: Session, user_id: int, days: int) -> dict:
    """Агрегация за последние N дней: суммы, среднее в день, сравнение с нормой."""
    start = today() - timedelta(days=days - 1)

    row = session.execute(
        select(
            func.count().label("n"),
            func.coalesce(func.sum(models.NutritionDay.protein), 0.0),
            func.coalesce(func.sum(models.NutritionDay.fat), 0.0),
            func.coalesce(func.sum(models.NutritionDay.carbs), 0.0),
            func.coalesce(func.sum(models.NutritionDay.calories), 0.0),
        ).where(
            models.NutritionDay.user_id == user_id,
            models.NutritionDay.day >= start,
        )
    ).one()

    n = row[0]
    totals = {"protein": float(row[1]), "fat": float(row[2]),
              "carbs": float(row[3]), "calories": float(row[4])}
    avg = {k: v / n if n else 0.0 for k, v in totals.items()}

    goal = get_goal(session, user_id)
    diff = None
    if goal is not None:
        diff = {
            "protein": round(avg["protein"] - goal.protein, 1),
            "fat": round(avg["fat"] - goal.fat, 1),
            "carbs": round(avg["carbs"] - goal.carbs, 1),
            "calories": round(avg["calories"] - goal.calories, 0),
        }

    return {
        "days_recorded": n,
        "period_days": days,
        "start": start.isoformat(),
        "end": today().isoformat(),
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "daily_avg": {k: round(v, 1) for k, v in avg.items()},
        "goal": ({"protein": goal.protein, "fat": goal.fat,
                  "carbs": goal.carbs, "calories": goal.calories} if goal else None),
        "diff_vs_goal": diff,
    }
