"""Общие утилиты времени: «сегодня» в часовом поясе приложения (MSK)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import settings


def today() -> date:
    """Сегодняшняя дата в часовом поясе приложения (MSK, а не серверный UTC)."""
    return datetime.now(ZoneInfo(settings.timezone)).date()
