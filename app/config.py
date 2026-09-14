"""Конфигурация приложения из переменных окружения / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки. Читаются из переменных окружения и файла .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Токен Telegram-бота (из BotFather). Секрет — не коммитить.
    bot_token: str = ""

    # Строка подключения к БД. По умолчанию SQLite (файл рядом с проектом).
    # Для продакшена: postgresql+psycopg2://user:pass@host:5432/dbname
    database_url: str = "sqlite:///./gym_tracker.db"

    # Часовой пояс, по которому считается «день». Для Максима — Москва.
    timezone: str = "Europe/Moscow"

    # Пауза long polling (сек) — время ожидания новых сообщений от Telegram.
    poll_timeout: int = 30


settings = Settings()
