# backend/Dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# OS deps (add gcc/gdal/etc. only if you need them)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && rm -rf /var/lib/apt/lists/*

# Copy deps first for better caching
COPY api/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Copy app
COPY api/ /app

# Env knobs for CORS & host/port
ENV APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

EXPOSE 8000

# Use uvicorn directly; swap to gunicorn+uvicorn workers if desired
# Example FastAPI entry: app/main.py contains "app = FastAPI()"
CMD ["sh", "-c", "uvicorn main:app --host ${APP_HOST} --port ${APP_PORT}"]
