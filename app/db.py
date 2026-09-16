"""Подключение к БД: движок, фабрика сессий, базовый класс моделей."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Для SQLite в памяти (тесты) нужен StaticPool, чтобы соединение не терялось.
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

# expire_on_commit=False: ORM-объекты, возвращаемые из run_db (sync в потоке),
# остаются читаемыми после commit + закрытия сессии (иначе DetachedInstanceError).
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


def init_db() -> None:
    """Создаёт все таблицы + лёгкая миграция для старых dev-БД."""
    from app import models  # noqa: F401  — регистрация моделей

    Base.metadata.create_all(engine)

    # Для старых SQLite-БД, где strength_logs уже есть без workout_id, добавляем
    # колонку на лету (SQLite не умеет ALTER ... ADD CONSTRAINT, поэтому без FK).
    if engine.dialect.name == "sqlite":
        with engine.connect() as conn:
            cols = [row[1] for row in conn.execute(text("PRAGMA table_info(strength_logs)"))]
            if "workout_id" not in cols:
                conn.execute(text(
                    "ALTER TABLE strength_logs ADD COLUMN workout_id INTEGER"
                ))
                conn.commit()
