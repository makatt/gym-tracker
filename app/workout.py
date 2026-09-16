"""Сервис тренировок: шаблоны, активная тренировка, сравнение с прошлым."""

from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models
from app.strength import ensure_exercise, estimate_1rm
from app.templates import DEFAULT_TEMPLATES
from app.timeutil import today


def seed_templates(session: Session, user_id: int) -> None:
    """Разворачивает стартовые шаблоны, если их ещё нет у пользователя."""
    for pos, (name, exercises) in enumerate(DEFAULT_TEMPLATES.items()):
        t = session.scalar(
            select(models.WorkoutTemplate).where(
                models.WorkoutTemplate.user_id == user_id,
                models.WorkoutTemplate.name == name,
            )
        )
        if t is None:
            t = models.WorkoutTemplate(user_id=user_id, name=name, position=pos)
            session.add(t)
            session.flush()
            for i, ex_name in enumerate(exercises):
                session.add(models.TemplateExercise(
                    template_id=t.id, name=ex_name, position=i))
    session.commit()


def list_templates(session: Session, user_id: int) -> list[dict]:
    """Все шаблоны пользователя с упражнениями в порядке выполнения."""
    seed_templates(session, user_id)
    rows = session.scalars(
        select(models.WorkoutTemplate)
        .where(models.WorkoutTemplate.user_id == user_id)
        .order_by(models.WorkoutTemplate.position)
    ).all()
    result = []
    for t in rows:
        exs = session.scalars(
            select(models.TemplateExercise.name)
            .where(models.TemplateExercise.template_id == t.id)
            .order_by(models.TemplateExercise.position)
        ).all()
        result.append({"name": t.name, "exercises": list(exs)})
    return result


def active_workout(session: Session, user_id: int) -> models.Workout | None:
    return session.scalar(
        select(models.Workout).where(
            models.Workout.user_id == user_id,
            models.Workout.is_active.is_(True),
        )
    )


def create_workout(
    session: Session,
    user_id: int,
    template_name: str | None,
    day: date | None = None,
) -> models.Workout:
    """Создаёт активную тренировку (закрывая предыдущую активную)."""
    old = active_workout(session, user_id)
    if old is not None:
        old.is_active = False
    w = models.Workout(
        user_id=user_id,
        day=day or today(),
        name=template_name,
        is_active=True,
    )
    session.add(w)
    session.commit()
    return w


def previous_entry(
    session: Session,
    user_id: int,
    exercise_name: str,
    exclude_workout_id: int | None = None,
) -> dict | None:
    """Последний подход по упражнению (вне указанной тренировки)."""
    ex = session.scalar(
        select(models.Exercise).where(
            models.Exercise.user_id == user_id,
            models.Exercise.name == exercise_name.strip().lower(),
        )
    )
    if ex is None:
        return None
    q = select(models.StrengthLog).where(models.StrengthLog.exercise_id == ex.id)
    if exclude_workout_id is not None:
        q = q.where(
            or_(
                models.StrengthLog.workout_id != exclude_workout_id,
                models.StrengthLog.workout_id.is_(None),
            )
        )
    row = session.scalars(
        q.order_by(models.StrengthLog.day.desc(), models.StrengthLog.id.desc())
    ).first()
    if row is None:
        return None
    return {
        "day": row.day.isoformat(),
        "weight": row.weight,
        "reps": row.reps,
        "e1rm": estimate_1rm(row.weight, row.reps),
    }


def log_to_workout(
    session: Session,
    user_id: int,
    name: str,
    weight: float,
    reps: int,
) -> models.StrengthLog | None:
    """Записывает подход в активную тренировку (повторная отправка перезаписывает)."""
    w = active_workout(session, user_id)
    if w is None:
        return None
    ex = ensure_exercise(session, user_id, name)
    row = session.scalar(
        select(models.StrengthLog).where(
            models.StrengthLog.workout_id == w.id,
            models.StrengthLog.exercise_id == ex.id,
        )
    )
    if row is None:
        row = models.StrengthLog(
            user_id=user_id, exercise_id=ex.id, workout_id=w.id,
            day=w.day, weight=weight, reps=reps,
        )
        session.add(row)
    else:
        row.weight = weight
        row.reps = reps
        row.day = w.day
    session.commit()
    return row


def workout_logs(session: Session, workout: models.Workout) -> list[models.StrengthLog]:
    return list(session.scalars(
        select(models.StrengthLog)
        .where(models.StrengthLog.workout_id == workout.id)
        .order_by(models.StrengthLog.id)
    ).all())


def workout_report(session: Session, workout: models.Workout) -> dict:
    """Сводка тренировки: текущие подходы + прошлые + изменение 1ПМ."""
    entries = {}
    for lg in workout_logs(session, workout):
        ex = session.get(models.Exercise, lg.exercise_id)
        prev = previous_entry(session, workout.user_id, ex.name,
                              exclude_workout_id=workout.id)
        cur = estimate_1rm(lg.weight, lg.reps)
        entries[ex.name] = {
            "current": {"weight": lg.weight, "reps": lg.reps, "e1rm": cur},
            "previous": prev,
            "delta_e1rm": round(cur - prev["e1rm"], 1) if prev else None,
        }
    return {"name": workout.name, "day": workout.day.isoformat(), "exercises": entries}


def finish_workout(session: Session, user_id: int) -> dict | None:
    """Закрывает активную тренировку и возвращает её сводку."""
    w = active_workout(session, user_id)
    if w is None:
        return None
    w.is_active = False
    session.commit()
    return workout_report(session, w)


def list_workouts(session: Session, user_id: int, limit: int = 10) -> list[dict]:
    """История тренировок (последние N)."""
    rows = session.scalars(
        select(models.Workout)
        .where(models.Workout.user_id == user_id)
        .order_by(models.Workout.day.desc(), models.Workout.id.desc())
        .limit(limit)
    ).all()
    out = []
    for w in rows:
        logs = workout_logs(session, w)
        out.append({
            "day": w.day.isoformat(),
            "name": w.name,
            "count": len(logs),
            "active": w.is_active,
        })
    return out
