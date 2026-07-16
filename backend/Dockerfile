# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Install system dependencies needed by some Python packages (libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.8.3 \
    POETRY_HOME=/opt/poetry \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="${POETRY_HOME}/bin:${PATH}"

WORKDIR /app

# Copy dependency manifests first for better layer caching.
# poetry.lock is optional — copy pyproject.toml unconditionally, then
# try to copy poetry.lock (Docker silently skips missing optional sources
# when using a wildcard that matches zero files).
COPY pyproject.toml ./

# Install production dependencies only (no dev extras, no editable install)
RUN poetry install --no-root --only main

# Copy the rest of the application source.
# When running with the docker-compose volume mount (./backend:/app),
# this layer is effectively overlaid at runtime, enabling hot-reload.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
