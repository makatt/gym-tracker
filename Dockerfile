FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Слои зависимостей кэшируются отдельно от кода.
COPY requirements.txt .
RUN pip install -r requirements.txt \
    # драйвер PostgreSQL — только в образе (для docker-compose с postgres)
    && pip install psycopg2-binary

COPY app/ app/
COPY static/ static/
COPY run_bot.py run_api.py ./

# Не root — best practice для контейнеров.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# По умолчанию — API; бот запускается отдельным сервисом в compose.
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
