"""REST API (FastAPI): здоровье, питание, нормы, силовые."""

from __future__ import annotations

from datetime import date

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import nutrition as svc
from app import strength as strength_svc
from app.db import SessionLocal, init_db
from app.parser import Macros

app = FastAPI(title="Gym Tracker API", version="0.1.0")


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


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "gym-tracker", "version": "0.1.0"}


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


@app.post("/api/strength")
def add_strength(payload: StrengthIn):
    with SessionLocal() as session:
        user = svc.ensure_user(session, payload.tg_id)
        strength_svc.log_strength(session, user.id, payload.exercise,
                                  payload.weight, payload.reps, payload.day)
    name = payload.exercise.strip().lower()
    return {"tg_id": payload.tg_id, "exercise": name, "weight": payload.weight,
            "reps": payload.reps,
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
