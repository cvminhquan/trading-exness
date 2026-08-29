FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install -e ".[dev]"

# Note: MT5 requires Windows + MetaTrader 5 terminal.
# This container is for development/testing of non-MT5 components.
# Production MT5 bot runs on Windows VPS.

CMD ["pytest", "-v"]
