"""Модуль тела: профиль, замеры, расчёт КБЖУ (BMR/TDEE), прогресс, фото.

Формулы:
- BMR по Миффлину–Сан Жеору
- TDEE = BMR × коэффициент активности
- цель: cut (−20%) / maintain / bulk (+10%)
- БЖУ: белки 2.0 г/кг, жиры 0.9 г/кг, углеводы — остаток калорий
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.timeutil import today

ACTIVITY_FACTORS = {
    1: 1.2,      # сидячий
    2: 1.375,    # лёгкая (1–3 тренировки/нед)
    3: 1.55,     # средняя (3–5)
    4: 1.725,    # высокая (6–7)
    5: 1.9,      # очень высокая (2 раза в день / физ. работа)
}

GOAL_ALIASES = {
    "сушка": "cut", "похудение": "cut", "cut": "cut", "дефицит": "cut",
    "набор": "bulk", "масса": "bulk", "bulk": "bulk", "профицит": "bulk",
    "поддержание": "maintain", "поддержка": "maintain", "maintain": "maintain",
}

SEX_ALIASES = {
    "м": "male", "male": "male", "m": "male", "муж": "male",
    "ж": "female", "female": "female", "f": "female", "жен": "female",
}


def normalize_sex(raw: str) -> str:
    return SEX_ALIASES.get(raw.strip().lower(), "")


def normalize_goal(raw: str) -> str:
    return GOAL_ALIASES.get(raw.strip().lower(), "")


def calculate_bmr(sex: str, weight: float, height: float, age: int) -> float:
    base = 10 * weight + 6.25 * height - 5 * age
    return base + 5 if sex == "male" else base - 161


def calculate_tdee(bmr: float, activity: int) -> float:
    return bmr * ACTIVITY_FACTORS.get(activity, 1.55)


def calculate_target(tdee: float, goal: str) -> float:
    if goal == "cut":
        return tdee * 0.8
    if goal == "bulk":
        return tdee * 1.1
    return tdee


def calculate_macros(target_kcal: float, weight: float) -> dict:
    protein = 2.0 * weight
    fat = 0.9 * weight
    carbs = max(0.0, (target_kcal - protein * 4 - fat * 9) / 4.0)
    return {"protein": round(protein, 1), "fat": round(fat, 1), "carbs": round(carbs, 1)}


# ---------- сервис ----------

def set_profile(session: Session, user_id: int, sex: str, height: float,
                birth_year: int, activity: int, goal: str) -> models.BodyProfile:
    p = session.scalar(select(models.BodyProfile).where(models.BodyProfile.user_id == user_id))
    if p is None:
        p = models.BodyProfile(user_id=user_id, sex=sex, height_cm=height,
                               birth_year=birth_year, activity=activity, goal=goal)
        session.add(p)
    else:
        p.sex, p.height_cm, p.birth_year, p.activity, p.goal = sex, height, birth_year, activity, goal
    session.commit()
    return p


def get_profile(session: Session, user_id: int) -> models.BodyProfile | None:
    return session.scalar(select(models.BodyProfile).where(models.BodyProfile.user_id == user_id))


def add_metric(session: Session, user_id: int, weight: float,
               body_fat: float | None = None, muscle: float | None = None,
               day: date | None = None) -> models.BodyMetric:
    m = models.BodyMetric(user_id=user_id, day=day or today(), weight_kg=weight,
                          body_fat_pct=body_fat, muscle_mass_kg=muscle)
    session.add(m)
    session.commit()
    return m


def metrics_history(session: Session, user_id: int, limit: int = 30) -> list[dict]:
    rows = session.scalars(
        select(models.BodyMetric)
        .where(models.BodyMetric.user_id == user_id)
        .order_by(models.BodyMetric.day.desc(), models.BodyMetric.id.desc())
        .limit(limit)
    ).all()
    return [
        {"day": r.day.isoformat(), "weight": r.weight_kg,
         "fat": r.body_fat_pct, "muscle": r.muscle_mass_kg}
        for r in rows
    ]


def latest_metric(session: Session, user_id: int) -> models.BodyMetric | None:
    return session.scalars(
        select(models.BodyMetric)
        .where(models.BodyMetric.user_id == user_id)
        .order_by(models.BodyMetric.day.desc(), models.BodyMetric.id.desc())
    ).first()


def progress(session: Session, user_id: int, limit: int = 15) -> dict:
    h = metrics_history(session, user_id, limit)
    if not h:
        return {"records": 0, "history": []}
    latest, oldest = h[0], h[-1]
    return {
        "records": len(h),
        "latest": latest,
        "oldest": oldest,
        "weight_delta": round(latest["weight"] - oldest["weight"], 1),
        "fat_delta": (round(latest["fat"] - oldest["fat"], 1)
                      if latest["fat"] is not None and oldest["fat"] is not None else None),
        "history": h,
    }


def add_photo(session: Session, user_id: int, path: str, caption: str | None = None) -> models.ProgressPhoto:
    p = models.ProgressPhoto(user_id=user_id, day=today(), file_path=path, caption=caption)
    session.add(p)
    session.commit()
    return p


def calc_kcal(session: Session, user_id: int) -> dict | None:
    """Расчёт КБЖУ на основе профиля + последнего замера веса."""
    p = get_profile(session, user_id)
    m = latest_metric(session, user_id)
    if p is None or m is None:
        return None
    age = today().year - p.birth_year
    bmr = calculate_bmr(p.sex, m.weight_kg, p.height_cm, age)
    tdee = calculate_tdee(bmr, p.activity)
    target = calculate_target(tdee, p.goal)
    macros = calculate_macros(target, m.weight_kg)
    return {
        "age": age, "weight": m.weight_kg, "sex": p.sex, "goal": p.goal,
        "bmr": round(bmr), "tdee": round(tdee), "target_kcal": round(target),
        "protein": macros["protein"], "fat": macros["fat"], "carbs": macros["carbs"],
    }
