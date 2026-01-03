#!/usr/bin/env bash
# Rebuild the local Docker image, restart the smoke container, and validate the HTTP API.
# The harness always publishes a random host port as recommended by Docker port publishing docs:
# https://docs.docker.com/engine/network/port-publishing/
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_TAG="article-extractor:local"
CONTAINER_NAME="article-extractor-smoke"
CONTAINER_PORT=13005
DATA_DIR="${PROJECT_ROOT}/tmp/docker-smoke-data"
MOUNT_TARGET="/var/article-extractor/storage"
HOST_STORAGE_FILE="${DATA_DIR}/storage_state.json"
CONTAINER_STORAGE_FILE="${MOUNT_TARGET}/storage_state.json"
SAMPLE_URL="https://en.wikipedia.org/wiki/Wikipedia"
HEALTH_TIMEOUT=60
LOGS_ALREADY_COLLECTED=0
LOG_PREFIX="[docker-debug]"
DIAGNOSTICS_FLAG="${ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS:-0}"

log() {
    printf '%s %s\n' "${LOG_PREFIX}" "$*"
}

die() {
    printf '%s ERROR: %s\n' "${LOG_PREFIX}" "$*" >&2
    exit 1
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        die "Missing required command: $1"
    fi
}

file_size() {
    if stat -c%s "$1" >/dev/null 2>&1; then
        stat -c%s "$1"
    else
        stat -f%z "$1"
    fi
}

allocate_port() {
    uv run python - <<'PY'
import socket

def pick_port() -> int:
    for _ in range(64):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("", 0))
            value = sock.getsockname()[1]
            if value >= 20000:
                return value
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]

print(pick_port())
PY
}

cleanup() {
    set +e
    if docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
        if [ "${LOGS_ALREADY_COLLECTED}" -eq 0 ]; then
            log "Collecting container logs before cleanup..."
            docker logs "${CONTAINER_NAME}" || true
        fi
        log "Stopping container ${CONTAINER_NAME}..."
        docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
    fi
    set -e
}

reset_storage_directory() {
    log "Deleting and recreating shared Playwright storage under ${DATA_DIR} ..."
    rm -rf "${DATA_DIR}"
    mkdir -p "${DATA_DIR}"
    uv run python -m article_extractor.storage "${DATA_DIR}"
    if [ ! -d "${DATA_DIR}" ]; then
        die "Storage directory ${DATA_DIR} could not be recreated"
    fi
}

trap cleanup EXIT INT TERM

require_command docker
require_command curl
require_command uv

log "Building ${IMAGE_TAG} ..."
docker build -t "${IMAGE_TAG}" "${PROJECT_ROOT}"

reset_storage_directory

HOST_PORT="$(allocate_port)"
if [ -z "${HOST_PORT}" ]; then
    die "Failed to allocate a host port"
fi

log "Chosen host port ${HOST_PORT} (container ${CONTAINER_PORT})"

if docker ps -a --format '{{.Names}}' | grep -Fxq "${CONTAINER_NAME}"; then
    log "Removing stale container ${CONTAINER_NAME} before restart"
    docker rm -f "${CONTAINER_NAME}" >/dev/null
fi

log "Starting container ${CONTAINER_NAME} ..."
CONTAINER_ID="$(
    docker run \
        -d \
        --name "${CONTAINER_NAME}" \
        --publish "${HOST_PORT}:${CONTAINER_PORT}" \
        --volume "${DATA_DIR}:${MOUNT_TARGET}" \
        -e TZ=UTC \
        -e HOST=0.0.0.0 \
        -e PORT="${CONTAINER_PORT}" \
        -e ARTICLE_EXTRACTOR_CACHE_SIZE=512 \
        -e ARTICLE_EXTRACTOR_THREADPOOL_SIZE=12 \
        -e ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT=true \
        -e ARTICLE_EXTRACTOR_STORAGE_STATE_FILE="${CONTAINER_STORAGE_FILE}" \
        -e ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS="${DIAGNOSTICS_FLAG}" \
        "${IMAGE_TAG}"
)"
log "Container ID: ${CONTAINER_ID}"

    if [ "${DIAGNOSTICS_FLAG}" != "0" ]; then
        log "Diagnostics logging enabled for this run (ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=${DIAGNOSTICS_FLAG})."
    fi

wait_for_health() {
    local tries=0
    local deadline=${HEALTH_TIMEOUT}
    while [ "${tries}" -lt "${deadline}" ]; do
        if curl --silent --show-error --max-time 2 "http://localhost:${HOST_PORT}/health" >/dev/null; then
            return 0
        fi
        sleep 1
        tries=$((tries + 1))
    done
    return 1
}

log "Waiting for /health to become ready (timeout ${HEALTH_TIMEOUT}s) ..."
if ! wait_for_health; then
    die "Server did not become healthy"
fi
log "Health check succeeded"

SMOKE_OUTPUT="$(mktemp)"
log "Issuing smoke POST request to http://localhost:${HOST_PORT}/ ..."
HTTP_CODE="$(
    curl \
        --silent \
        --show-error \
        --write-out '%{http_code}' \
        --output "${SMOKE_OUTPUT}" \
        -X POST "http://localhost:${HOST_PORT}/" \
        -H 'Content-Type: application/json' \
        --data "{\"url\":\"${SAMPLE_URL}\"}"
)"
log "Smoke request HTTP status: ${HTTP_CODE}"

log "Response preview:"
head -n 40 "${SMOKE_OUTPUT}" || true
rm -f "${SMOKE_OUTPUT}"

if [ "${HTTP_CODE}" != "200" ]; then
    die "Smoke request failed with HTTP status ${HTTP_CODE}"
fi

if [ -f "${HOST_STORAGE_FILE}" ]; then
    SIZE_BYTES="$(file_size "${HOST_STORAGE_FILE}")"
    if [ "${SIZE_BYTES}" -le 0 ]; then
        die "Playwright storage file ${HOST_STORAGE_FILE} is empty"
    fi
    log "Playwright storage recreated at ${HOST_STORAGE_FILE} (${SIZE_BYTES} bytes)"
else
    die "Expected storage file ${HOST_STORAGE_FILE} was not created"
fi

log "Container logs (tail 60):"
docker logs "${CONTAINER_NAME}" --tail 60 || true
LOGS_ALREADY_COLLECTED=1

cat <<EOF
[docker-debug] Ready-to-run curl command:
  curl -X POST http://localhost:${HOST_PORT}/ \
       -H 'Content-Type: application/json' \
       --data '{"url":"${SAMPLE_URL}"}'

[docker-debug] When finished, the harness will clean up the container automatically.
EOF

log "Shutting down ${CONTAINER_NAME} ..."
docker rm -f "${CONTAINER_NAME}" >/dev/null

log "Docker validation harness completed successfully"
