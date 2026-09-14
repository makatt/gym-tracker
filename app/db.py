"""Подключение к БД: движок, фабрика сессий, базовый класс моделей."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# Для SQLite в памяти (тесты) нужен StaticPool, чтобы соединение не терялось.
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


def init_db() -> None:
    """Создаёт все таблицы (для MVP; в проде — Alembic-миграции)."""
    from app import models  # noqa: F401  — регистрация моделей

    Base.metadata.create_all(engine)
