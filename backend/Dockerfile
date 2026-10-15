# CEREBRO API
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps for argon2-cffi and psycopg, removed from the final layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . \
    && apt-get purge -y build-essential && apt-get autoremove -y

COPY alembic.ini ./
COPY alembic ./alembic

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 cerebro

# The filesystem object store's root, created here and owned by the runtime
# user. This is not cosmetic: a named volume or an emptyDir mounted over a path
# that does not exist in the image is created owned by root, and the API —
# running as uid 10001 — then cannot create the per-owner directory inside it.
# Uploads fail with a bare 500. Docker initialises an empty named volume from
# the image's directory, ownership included, so creating it here is what makes
# the mount writable.
ENV CEREBRO_STORAGE_PATH=/data/artifacts
RUN mkdir -p /data/artifacts && chown -R 10001:10001 /data

USER cerebro

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
