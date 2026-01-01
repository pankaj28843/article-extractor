# syntax=docker/dockerfile:1.6

# Multi-architecture Dockerfile for article-extractor HTTP server
# Supports both linux/amd64 and linux/arm64 platforms
# Production-ready with uvicorn, health checks, and multi-worker support

ARG PYTHON_VERSION=3.14-slim
ARG UV_VERSION=0.4.24

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# Build stage: install dependencies with uv using cached layers
FROM python:${PYTHON_VERSION} AS builder

COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy lockfiles first to maximize cache hits
COPY pyproject.toml uv.lock README.md LICENSE ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev --no-editable --extra server --extra httpx

# Copy remaining source after deps are installed
COPY src/ ./src/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --extra server --extra httpx

# Runtime stage - minimal image
FROM python:${PYTHON_VERSION} AS runtime

# Labels for container metadata
LABEL org.opencontainers.image.title="article-extractor" \
      org.opencontainers.image.description="Pure-Python article extraction HTTP service - Drop-in replacement for readability-js-server" \
      org.opencontainers.image.url="https://github.com/pankaj28843/article-extractor" \
      org.opencontainers.image.source="https://github.com/pankaj28843/article-extractor" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.authors="Pankaj Kumar Singh <pankaj28843@gmail.com>"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=3000 \
    LOG_LEVEL=info \
    WEB_CONCURRENCY=2 \
    APP_USER=appuser \
    APP_GROUP=appgroup

# Install curl for health checks
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd --gid 1000 ${APP_GROUP} && \
    useradd --uid 1000 --gid ${APP_GROUP} --shell /bin/bash --create-home ${APP_USER}

WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Set PATH to use virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER ${APP_USER}

# Expose port
EXPOSE 3000

# Health check - use the /health endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS --max-time 2 http://localhost:3000/health || exit 1

# Default: Run uvicorn server
CMD ["sh", "-c", "exec uvicorn article_extractor.server:app --host ${HOST:-0.0.0.0} --port ${PORT:-3000} --log-level ${LOG_LEVEL:-info} --proxy-headers --forwarded-allow-ips='*' --lifespan=auto --workers ${WEB_CONCURRENCY:-2}"]
