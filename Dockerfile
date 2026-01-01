# Multi-architecture Dockerfile for article-extractor
# Supports both linux/amd64 and linux/arm64 platforms

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
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-editable

# Copy source code
COPY src/ ./src/
COPY README.md LICENSE ./

# Install the package
RUN uv pip install --no-deps .

# Runtime stage - minimal image
FROM python:3.12-slim AS runtime

# Labels for container metadata
LABEL org.opencontainers.image.title="article-extractor" \
      org.opencontainers.image.description="Pure-Python article extraction library using Readability-style scoring" \
      org.opencontainers.image.url="https://github.com/pankaj28843/article-extractor" \
      org.opencontainers.image.source="https://github.com/pankaj28843/article-extractor" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.authors="Pankaj Kumar Singh <pankaj28843@gmail.com>"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Run as non-root user
    APP_USER=appuser \
    APP_GROUP=appgroup

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

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from article_extractor import extract_article; print('OK')" || exit 1

# Default command - can be overridden
CMD ["python", "-c", "from article_extractor import extract_article; print('article-extractor ready')"]
