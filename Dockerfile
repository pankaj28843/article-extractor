# Multi-architecture Dockerfile for article-extractor HTTP server
# Supports both linux/amd64 and linux/arm64 platforms
# Production-ready with uvicorn, health checks, and multi-worker support

# Build stage
FROM python:3.12-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock README.md ./

# Copy source code (needed for package build)
COPY src/ ./src/
COPY LICENSE ./

# Install dependencies with server support and build package
RUN uv sync --frozen --no-dev --no-editable --extra server --extra httpx

# Runtime stage - minimal image
FROM python:3.12-slim AS runtime

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
    # Server configuration
    HOST=0.0.0.0 \
    PORT=3000 \
    LOG_LEVEL=info \
    # Run as non-root user
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

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Set PATH to use virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER ${APP_USER}

# Expose port
EXPOSE 3000

# Health check - use the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Default: Run uvicorn server
# Override with: docker run article-extractor article-extractor <url>
CMD ["uvicorn", "article_extractor.server:app", "--host", "0.0.0.0", "--port", "3000"]
