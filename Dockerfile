# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

LABEL org.opencontainers.image.title="Global UAV Visual Atlas 2026" \
      org.opencontainers.image.description="Resumable pipeline building an auditable global UAV registry and visual atlas." \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UAV_DB_PATH=/app/data/uav_atlas.sqlite

# Pillow needs the imaging libraries; sqlite3 is used by the operations scripts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
        libwebp7 \
        libfreetype6 \
        sqlite3 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY agents ./agents
COPY crawlers ./crawlers
COPY scripts ./scripts
COPY tests ./tests
COPY run.py pyproject.toml ./
COPY data/seed ./data/seed

# Volumes are mounted over these in compose; create them so a bare `docker run`
# still works.
RUN mkdir -p /app/data/cache /app/data/imports /app/images /app/output /app/logs /app/docs \
    && useradd --create-home --uid 10001 atlas \
    && chown -R atlas:atlas /app
USER atlas

# Healthy = migrations apply and the schema verifies.
HEALTHCHECK --interval=60s --timeout=20s --start-period=15s --retries=3 \
    CMD python -c "from app.db import connect, migrate, verify_schema; c=connect(); migrate(c); verify_schema(c); print('ok')" || exit 1

ENTRYPOINT ["python", "run.py"]
CMD ["--all", "--resume"]
