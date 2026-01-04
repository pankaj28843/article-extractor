# syntax=docker/dockerfile:1.6

# Single-stage Dockerfile using the official uv Debian image
# Keeps dependency installs cached while letting source/docs change freely

ARG UV_VERSION=0.9.21-debian
ARG APP_USER=appuser
ARG APP_GROUP=appgroup
ARG APP_UID=1000
ARG APP_GID=1000
ARG TARGETARCH

FROM ghcr.io/astral-sh/uv:${UV_VERSION}

ARG APP_USER
ARG APP_GROUP
ARG APP_UID
ARG APP_GID
ARG TARGETARCH

USER root

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=300 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=3000 \
    LOG_LEVEL=info \
    ARTICLE_EXTRACTOR_LOG_LEVEL=info \
    ARTICLE_EXTRACTOR_LOG_FORMAT=json \
    WEB_CONCURRENCY=2 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# System dependencies for Playwright + curl for health checks
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libatspi2.0-0 \
        libcairo2 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 && \
    rm -rf /var/lib/apt/lists/*

# Create or reuse a non-root user/group that matches provided IDs
RUN set -eux; \
    if getent group "${APP_GID}" >/dev/null; then \
        existing_group="$(getent group "${APP_GID}" | cut -d: -f1)"; \
        if [ "$existing_group" != "${APP_GROUP}" ]; then \
            groupmod -n "${APP_GROUP}" "$existing_group"; \
        fi; \
    else \
        groupadd --gid "${APP_GID}" "${APP_GROUP}"; \
    fi; \
    if getent passwd "${APP_UID}" >/dev/null; then \
        existing_user="$(getent passwd "${APP_UID}" | cut -d: -f1)"; \
        usermod -l "${APP_USER}" -d "/home/${APP_USER}" -m "$existing_user"; \
        usermod -g "${APP_GID}" "${APP_USER}"; \
    else \
        useradd --uid "${APP_UID}" --gid "${APP_GID}" --shell /bin/bash --create-home "${APP_USER}"; \
    fi; \
    mkdir -p /home/${APP_USER}/app && chown -R ${APP_USER}:${APP_GROUP} /home/${APP_USER}

RUN mkdir -p ${PLAYWRIGHT_BROWSERS_PATH} && chown ${APP_USER}:${APP_GROUP} ${PLAYWRIGHT_BROWSERS_PATH}

ENV HOME=/home/${APP_USER}
WORKDIR /home/${APP_USER}/app

LABEL org.opencontainers.image.title="article-extractor" \
      org.opencontainers.image.description="Pure-Python article extraction HTTP service - Drop-in replacement for readability-js-server" \
      org.opencontainers.image.url="https://github.com/pankaj28843/article-extractor" \
      org.opencontainers.image.source="https://github.com/pankaj28843/article-extractor" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.authors="Pankaj Kumar Singh <pankaj28843@gmail.com>"

USER ${APP_USER}

# blank README and LICENSE to allow caching of dependency layer
RUN touch README.md LICENSE

# Copy dependency manifests first to maximize caching of uv sync
COPY --chown=${APP_USER}:${APP_GROUP} pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/home/${APP_USER}/.cache/uv,id=uv-cache-${TARGETARCH},uid=${APP_UID},gid=${APP_GID} \
    uv sync --locked --no-install-project --no-dev --no-editable --extra server --extra httpx --extra playwright
    
# Preinstall Playwright browsers inside the image
RUN uv run playwright install --only-shell chromium

# Copy source and docs after dependencies are cached
COPY --chown=${APP_USER}:${APP_GROUP} src/ ./src/
COPY --chown=${APP_USER}:${APP_GROUP} README.md LICENSE ./

# Editable install keeps dependency layer stable while allowing code changes
RUN --mount=type=cache,target=/home/${APP_USER}/.cache/uv,id=uv-cache-${TARGETARCH},uid=${APP_UID},gid=${APP_GID} \
    uv pip install --no-deps -e .

ENV PATH="/home/${APP_USER}/app/.venv/bin:$PATH"

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -fsS --max-time 2 http://localhost:3000/health || exit 1

# Default: Run uvicorn server
CMD ["sh", "-c", "exec uvicorn article_extractor.server:app --host ${HOST:-0.0.0.0} --port ${PORT:-3000} --log-level ${LOG_LEVEL:-info} --proxy-headers --forwarded-allow-ips='*' --lifespan=auto --workers ${WEB_CONCURRENCY:-2}"]
