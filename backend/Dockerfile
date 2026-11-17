# -----------------------------------------------------------------------------
# Python Backend for Azure Container Apps
# -----------------------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app/backend

# Install uv from official Astral image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install backend dependencies using locked uv manifest
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Copy backend application source code
COPY . ./

# Create non-root system user and configure directory permissions
RUN groupadd -r appuser && useradd -r -g appuser -u 10001 -d /app appuser \
    && mkdir -p /app/backend/data/uploads \
    && chown -R appuser:appuser /app

# Switch to non-root execution
USER appuser

# Azure Container Apps injects PORT (defaults to 8000)
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uv run --locked --no-sync python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
