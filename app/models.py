"""ORM-модели: пользователи, питание, силовые, тренировки и шаблоны."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    """Пользователь бота (по tg_id)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NutritionDay(Base):
    """Итоговые БЖУ и калории за один день (из Yazio)."""

    __tablename__ = "nutrition_days"
    __table_args__ = (
        UniqueConstraint("user_id", "day", name="uq_nutrition_user_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    protein: Mapped[float] = mapped_column(Float)
    fat: Mapped[float] = mapped_column(Float)
    carbs: Mapped[float] = mapped_column(Float)
    calories: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Goal(Base):
    """Норма БЖУ/калорий пользователя."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    protein: Mapped[float] = mapped_column(Float)
    fat: Mapped[float] = mapped_column(Float)
    carbs: Mapped[float] = mapped_column(Float)
    calories: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Exercise(Base):
    """Упражнение пользователя (уникально по имени для каждого пользователя)."""

    __tablename__ = "exercises"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_exercise_user_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))


class Workout(Base):
    """Одна тренировка: набор подходов в конкретный день (например «спина»)."""

    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    pending_exercise: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorkoutTemplate(Base):
    """Шаблон тренировочного дня (спина / грудь / руки)."""

    __tablename__ = "workout_templates"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_template_user_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer, default=0)


class TemplateExercise(Base):
    """Упражнение внутри шаблона (в порядке выполнения)."""

    __tablename__ = "template_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("workout_templates.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0)


class StrengthLog(Base):
    """Один подход: упражнение → вес × повторения (опционально в рамках тренировки)."""

    __tablename__ = "strength_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), index=True)
    workout_id: Mapped[int | None] = mapped_column(
        ForeignKey("workouts.id"), nullable=True, index=True
    )
    day: Mapped[date] = mapped_column(Date, index=True)
    weight: Mapped[float] = mapped_column(Float)
    reps: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class BodyProfile(Base):
    """База для расчёта КБЖУ: пол, рост, год рождения, активность, цель."""

    __tablename__ = "body_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    sex: Mapped[str] = mapped_column(String(8))          # male / female
    height_cm: Mapped[float] = mapped_column(Float)
    birth_year: Mapped[int] = mapped_column(Integer)
    activity: Mapped[int] = mapped_column(Integer)        # 1–5
    goal: Mapped[str] = mapped_column(String(16))         # cut / maintain / bulk
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class BodyMetric(Base):
    """Снимок тела на дату: вес, % жира, мышечная масса."""

    __tablename__ = "body_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    muscle_mass_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ProgressPhoto(Base):
    """Фото прогресса (визуальный журнал)."""

    __tablename__ = "progress_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    file_path: Mapped[str] = mapped_column(String(255))
    caption: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
