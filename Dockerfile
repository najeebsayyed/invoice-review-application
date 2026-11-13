# -----------------------------------------------------------------------------
# Stage 1: Build the React 19 Frontend
# -----------------------------------------------------------------------------
FROM node:22-slim AS frontend-builder
WORKDIR /app/frontend

# Enable pnpm via Corepack
RUN corepack enable && corepack prepare pnpm@latest --activate

# Cache and install dependencies
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml* ./
RUN pnpm install --frozen-lockfile

# Copy frontend source and compile static bundle
COPY frontend/ ./
# VITE_API_BASE_URL=/ ensures all API requests stay relative to the same origin
ENV VITE_API_BASE_URL=/
RUN pnpm build

# -----------------------------------------------------------------------------
# Stage 2: Python Backend with uv
# -----------------------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies (curl and certificates for uv installer)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
ADD https://astral.sh/uv/0.6.5/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

# Install backend dependencies using locked uv manifest
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Copy backend application source code
COPY backend/ ./

# Copy compiled frontend from Stage 1 into /app/frontend/dist
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Create runtime directories for SQLite database and document uploads
RUN mkdir -p /app/backend/data/uploads

# Render injects $PORT dynamically (defaults to 8000 locally)
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uv run --locked --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
