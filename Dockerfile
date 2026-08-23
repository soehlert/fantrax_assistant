FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy project definition and install dependencies
COPY pyproject.toml /app/
RUN uv sync --no-dev --no-install-project

# Copy source code, scripts, and initial data
COPY src /app/src
COPY scripts /app/scripts
COPY data /app/data

# Sync the project itself
RUN uv sync --no-dev

EXPOSE 8000

# Seed database on start if needed, then run FastAPI server
CMD ["sh", "-c", "uv run python scripts/fetch_all_data.py && uv run uvicorn web.main:app --host 0.0.0.0 --port 8000"]
