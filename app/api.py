"""REST API (FastAPI): питание, силовые, тренировки, тело."""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import body as body_svc
from app import nutrition as svc
from app import strength as strength_svc
from app import workout as workout_svc
from app.db import SessionLocal, init_db
from app.parser import Macros

app = FastAPI(title="Gym Tracker API", version="0.3.0")


class NutritionIn(BaseModel):
    tg_id: int
    day: date | None = None
    protein: float = Field(gt=0)
    fat: float = Field(gt=0)
    carbs: float = Field(gt=0)
    calories: float = Field(gt=0)


class GoalIn(BaseModel):
    tg_id: int
    protein: float = Field(gt=0)
    fat: float = Field(gt=0)
    carbs: float = Field(gt=0)
    calories: float = Field(gt=0)


class StrengthIn(BaseModel):
    tg_id: int
    exercise: str
    weight: float = Field(gt=0)
    reps: int = Field(ge=1)
    day: date | None = None


class WorkoutIn(BaseModel):
    tg_id: int
    name: str | None = None
    day: date | None = None


class WorkoutLogIn(BaseModel):
    tg_id: int
    exercise: str
    weight: float = Field(gt=0)
    reps: int = Field(ge=1)


class WorkoutDoneIn(BaseModel):
    tg_id: int


class ProfileIn(BaseModel):
    tg_id: int
    sex: str
    height_cm: float = Field(gt=0)
    birth_year: int
    activity: int = Field(ge=1, le=5)
    goal: str


class BodyMetricIn(BaseModel):
    tg_id: int
    weight: float = Field(gt=0)
    body_fat: float | None = None
    muscle: float | None = None
    day: date | None = None


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "gym-tracker", "version": "0.3.0"}


# ---------- питание ----------

@app.post("/api/nutrition")
def add_nutrition(payload: NutritionIn):
    with SessionLocal() as session:
        user = svc.ensure_user(session, payload.tg_id)
        day = payload.day or svc.today()
        row = svc.upsert_day(session, user.id, day,
                             Macros(payload.protein, payload.fat, payload.carbs, payload.calories))
        return {"tg_id": payload.tg_id, "day": row.day.isoformat(),
                "protein": row.protein, "fat": row.fat,
                "carbs": row.carbs, "calories": row.calories}


@app.post("/api/goals")
def add_goal(payload: GoalIn):
    with SessionLocal() as session:
        user = svc.ensure_user(session, payload.tg_id)
        goal = svc.set_goal(session, user.id,
                            Macros(payload.protein, payload.fat, payload.carbs, payload.calories))
        return {"tg_id": payload.tg_id, "protein": goal.protein, "fat": goal.fat,
                "carbs": goal.carbs, "calories": goal.calories}


@app.get("/api/summary/{tg_id}")
def get_summary(tg_id: int, days: int = 7):
    with SessionLocal() as session:
        user = svc.ensure_user(session, tg_id)
        return svc.summary(session, user.id, days)


@app.get("/api/day/{tg_id}")
def get_day(tg_id: int, day: date | None = None):
    with SessionLocal() as session:
        user = svc.ensure_user(session, tg_id)
        row = svc.get_day(session, user.id, day or svc.today())
        if row is None:
            raise HTTPException(status_code=404, detail="Записей за этот день нет")
        return {"tg_id": tg_id, "day": row.day.isoformat(), "protein": row.protein,
                "fat": row.fat, "carbs": row.carbs, "calories": row.calories}


# ---------- силовые ----------

@app.post("/api/strength")
def add_strength(payload: StrengthIn):
    with SessionLocal() as session:
        user = svc.ensure_user(session, payload.tg_id)
        strength_svc.log_strength(session, user.id, payload.exercise,
                                  payload.weight, payload.reps, payload.day)
    return {"tg_id": payload.tg_id, "exercise": payload.exercise.strip().lower(),
            "weight": payload.weight, "reps": payload.reps,
            "e1rm": strength_svc.estimate_1rm(payload.weight, payload.reps)}


@app.get("/api/exercises/{tg_id}")
def get_exercises(tg_id: int):
    with SessionLocal() as session:
        user = svc.ensure_user(session, tg_id)
        return {"exercises": strength_svc.list_exercises(session, user.id)}


@app.get("/api/strength/{tg_id}/{exercise}")
def get_strength_history(tg_id: int, exercise: str):
    with SessionLocal() as session:
        user = svc.ensure_user(session, tg_id)
        return {"exercise": exercise,
                "history": strength_svc.history(session, user.id, exercise)}


@app.get("/api/strength/progress/{tg_id}/{exercise}")
def get_strength_progress(tg_id: int, exercise: str):
    with SessionLocal() as session:
        user = svc.ensure_user(session, tg_id)
        return strength_svc.progress(session, user.id, exercise)


# ---------- тренировки ----------

@app.post("/api/workout")
def start_workout(payload: WorkoutIn):
    with SessionLocal() as session:
        user = svc.ensure_user(session, payload.tg_id)
        w = workout_svc.create_workout(session, user.id, payload.name, payload.day)
        templates = workout_svc.list_templates(session, user.id)
        template = next((t for t in templates if t["name"] == payload.name), None)
        return {"workout_id": w.id, "name": w.name, "day": w.day.isoformat(),
                "template": template}


@app.post("/api/workout/log")
def log_workout(payload: WorkoutLogIn):
    with SessionLocal() as session:
        user = svc.ensure_user(session, payload.tg_id)
        row = workout_svc.log_to_workout(session, user.id, payload.exercise,
                                         payload.weight, payload.reps)
        if row is None:
            raise HTTPException(status_code=400, detail="Нет активной тренировки")
        return {"exercise": payload.exercise.strip().lower(),
                "weight": payload.weight, "reps": payload.reps}


@app.post("/api/workout/done")
def done_workout(payload: WorkoutDoneIn):
    with SessionLocal() as session:
        user = svc.ensure_user(session, payload.tg_id)
        rep = workout_svc.finish_workout(session, user.id)
        if rep is None:
            raise HTTPException(status_code=400, detail="Нет активной тренировки")
        return rep


@app.get("/api/workouts/{tg_id}")
def list_workouts(tg_id: int):
    with SessionLocal() as session:
        user = svc.ensure_user(session, tg_id)
        return {"workouts": workout_svc.list_workouts(session, user.id)}


# ---------- тело ----------

@app.post("/api/profile")
def set_profile(payload: ProfileIn):
    sex = body_svc.normalize_sex(payload.sex)
    goal = body_svc.normalize_goal(payload.goal)
    if not sex:
        raise HTTPException(status_code=400, detail="Пол: м или ж")
    if not goal:
        raise HTTPException(status_code=400, detail="Цель: сушка / поддержание / набор")
    with SessionLocal() as session:
        user = svc.ensure_user(session, payload.tg_id)
        p = body_svc.set_profile(session, user.id, sex, payload.height_cm,
                                 payload.birth_year, payload.activity, goal)
    return {"tg_id": payload.tg_id, "sex": p.sex, "height_cm": p.height_cm,
            "birth_year": p.birth_year, "activity": p.activity, "goal": p.goal}


@app.post("/api/body")
def add_body_metric(payload: BodyMetricIn):
    with SessionLocal() as session:
        user = svc.ensure_user(session, payload.tg_id)
        m = body_svc.add_metric(session, user.id, payload.weight,
                                payload.body_fat, payload.muscle, payload.day)
    return {"tg_id": payload.tg_id, "day": m.day.isoformat(), "weight": m.weight_kg,
            "body_fat": m.body_fat_pct, "muscle": m.muscle_mass_kg}


@app.get("/api/kcal/{tg_id}")
def get_kcal(tg_id: int):
    with SessionLocal() as session:
        user = svc.ensure_user(session, tg_id)
        k = body_svc.calc_kcal(session, user.id)
        if k is None:
            raise HTTPException(status_code=400, detail="Нужны профиль и замер веса")
        return k


@app.get("/api/body/progress/{tg_id}")
def get_body_progress(tg_id: int):
    with SessionLocal() as session:
        user = svc.ensure_user(session, tg_id)
        return body_svc.progress(session, user.id)
