# Article Extractor

[![PyPI version](https://img.shields.io/pypi/v/article-extractor.svg)](https://pypi.org/project/article-extractor/)
![Python versions](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml/badge.svg)](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pankaj28843/article-extractor/branch/main/graph/badge.svg)](https://codecov.io/gh/pankaj28843/article-extractor)

High-fidelity article extraction in pure Python: library, HTTP API, and CLI that turn messy web pages into clean Markdown or HTML for ingestion, archiving, and LLM pipelines.

> Requires Python 3.12+

## Who This Helps

- Backend, data, and tooling teams that need reliable article text for search, RAG, or analytics.
- Engineers who prefer a single-language stack with fast installs and reproducible results.
- Teams that want a ready-to-ship server/CLI and a composable Python API.

## Quick Start (pick one)

### CLI (fastest)

```bash
pip install article-extractor
article-extractor https://en.wikipedia.org/wiki/Wikipedia --output markdown
```

You will see clean Markdown printed to stdout along with detected title, excerpt, and word count.

### Server (Docker)

```bash
docker run -p 3000:3000 ghcr.io/pankaj28843/article-extractor:latest
curl -XPOST http://localhost:3000/ \
    -H "Content-Type: application/json" \
    -d '{"url": "https://en.wikipedia.org/wiki/Wikipedia"}' | jq '.title, .word_count'
```

### Override cache + Playwright storage in Docker

- `docker run -e` lets you pass environment variables into the container so you can raise or lower the LRU cache limit (`ARTICLE_EXTRACTOR_CACHE_SIZE`, `ARTICLE_EXTRACTOR_THREADPOOL_SIZE`, etc.) without rebuilding images [Docker container run – env](https://docs.docker.com/reference/cli/docker/container/run/#env) #techdocs.
- Use `-v/--volume` to mount host directories and persist assets like the Playwright storage-state file between runs [Docker container run – volume](https://docs.docker.com/reference/cli/docker/container/run/#volume) #techdocs.
- `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE` is a project-scoped alias for the legacy `PLAYWRIGHT_STORAGE_STATE_FILE`. Set either one (alias wins) to keep cookies/session data on a mounted volume. `ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT` (defaults to `true`) controls which fetcher the server prefers when both Playwright and httpx are installed.
- Example: keep Playwright cookies on the host, force Playwright as the default fetcher, and increase the cache to 2k entries while running the published image:

```bash
docker run --rm -p 3000:3000 \
    -e ARTICLE_EXTRACTOR_CACHE_SIZE=2000 \
    -e ARTICLE_EXTRACTOR_STORAGE_STATE_FILE=/data/storage-state.json \
    -e ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT=true \
    -v $HOME/.article-extractor:/data \
    ghcr.io/pankaj28843/article-extractor:latest
```

Mounting the host directory ensures `/data/storage-state.json` survives container restarts, so Playwright-headed sessions can defeat bot checks once and reuse the same cookies later.

### Python Library

```python
from article_extractor import extract_article

html = """
<html><body><article><h1>Title</h1><p>Content...</p></article></body></html>
"""

result = extract_article(html, url="https://example.com/demo")
print(result.title)
print(result.markdown.splitlines()[0])
print(f"Words: {result.word_count}")
```

## Why Teams Choose Article Extractor

- Accuracy first: Readability-style scoring tuned for long-form content and docs.
- Clean output: GFM-ready Markdown and sanitised HTML safe for downstream pipelines.
- Speed at scale: Caching plus early-termination heuristics keep typical pages in 50–150 ms.
- Drop-in everywhere: Same engine across CLI, HTTP server, and Python API.
- Test coverage that catches regressions before you do.

## Installation

```bash
pip install article-extractor[server]  # HTTP server
pip install article-extractor[all]     # All optional extras

# Or with uv (fast installs)
uv add article-extractor --extra server
```

## HTTP Server

```bash
# Local
uvicorn article_extractor.server:app --host 0.0.0.0 --port 3000

# Docker
docker run -d -p 3000:3000 --name article-extractor \
    --restart unless-stopped ghcr.io/pankaj28843/article-extractor:latest
```

Endpoints:

- POST / — Extract article (`{"url": "..."}`)
- GET / — Service info
- GET /health — Health check
- GET /docs — Interactive OpenAPI UI

## CLI

```bash
# Extract from URL
article-extractor https://en.wikipedia.org/wiki/Wikipedia

# From file
article-extractor --file article.html --output markdown

# One-off via Docker
docker run --rm ghcr.io/pankaj28843/article-extractor:latest \
    article-extractor https://en.wikipedia.org/wiki/Wikipedia --output text
```

### Networking controls (CLI & Server)

- Honor corporate proxies automatically: `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY` are folded into every fetcher, or override them with `--proxy=http://user:pass@proxy:8080` and optional `--prefer-httpx/--prefer-playwright` flags.
- Rotate or pin User-Agents: pass `--user-agent` for deterministic runs or `--random-user-agent` to synthesize realistic desktop headers with [`fake-useragent`](https://pypi.org/project/fake-useragent/) (`pip install article-extractor[ua]` or use the `all`/`server` extras). Disable later via `--no-random-user-agent`.
- Handle bot challenges: `--headed --user-interaction-timeout 30` launches Chromium with a visible window, pauses for manual CAPTCHA solving, and persists cookies to `~/.article-extractor/storage_state.json` (override with `--storage-state`).
- Docker and server mode forward the same defaults. When running the FastAPI server, the CLI seeds these values so all requests inherit them unless the POST body supplies `{"prefer_playwright": false, "network": {"proxy": "http://", "headed": true, ...}}`.

Server POST example with overrides:

```json
{
    "url": "https://example.com/paywalled",
    "prefer_playwright": true,
    "network": {
        "user_agent": "MyMonitor/1.0",
        "random_user_agent": false,
        "proxy": "http://proxy.internal:8080",
        "proxy_bypass": ["metadata.internal"],
        "headed": true,
        "user_interaction_timeout": 25,
        "storage_state": "/var/lib/article-extractor/storage_state.json"
    }
}
```

## Observability

- Structured logs stream to stderr/stdout in JSON by default so Docker logging drivers and `journald` can parse them. Switch to text locally via `--log-format text` (CLI) or `ARTICLE_EXTRACTOR_LOG_FORMAT=text` (server/CLI/env files).
- Control verbosity with `--log-level` (`critical` default for CLI) or `ARTICLE_EXTRACTOR_LOG_LEVEL`. The FastAPI server defaults to `INFO` unless overridden.
- URLs in log entries are sanitized (`https://host/path` without query strings or credentials) to avoid leaking secrets.
- Deep fetch diagnostics (httpx retries, Playwright storage metadata) stay muted by default; flip them on with `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1` before running either the CLI or FastAPI server when you need per-request breadcrumbs. Leave it at `0` (default) to keep production logs lean.
- Every HTTP response includes an `X-Request-ID` (echoing inbound headers when provided). 500/422 responses also embed the request id in the JSON payload so you can cross-reference logs quickly.

When triaging locally you can combine the diagnostics flag with the CLI:

```bash
ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1 uv run article-extractor https://example.com
```

### Log Shipping Recipes

- **Docker logging drivers**: Containers keep writing newline-delimited JSON to stdout/stderr, so you can wire them into drivers like `fluentd`, `gelf`, or `local`. Per the official [Docker logging driver guide](https://docs.docker.com/engine/logging/configure/), start the server container with:

    ```bash
    docker run \
        --log-driver fluentd \
        --log-opt fluentd-address=host.docker.internal:24224 \
        --log-opt tag=article-extractor \
        -e ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1 \
        pankaj28843/article-extractor:latest
    ```

    This streams JSON logs (plus the optional diagnostics fields) straight into Fluent Bit/Fluentd without touching the application code.

- **Fluent Bit → Elasticsearch (ELK) pipeline**: Point the logging driver at a Fluent Bit sidecar that forwards to Elasticsearch/Kibana.

    ```ini
    # fluent-bit.conf
    [INPUT]
            Name    forward
            Listen  0.0.0.0
            Port    24224

    [FILTER]
            Name    modify
            Match   article-extractor
            Add     service article-extractor

    [OUTPUT]
            Name    es
            Match   *
            Host    elasticsearch
            Port    9200
            Index   article-extractor-logs
    ```

    Compose this with the Docker logging driver snippet above and Kibana immediately ingests request/diagnostic fields for dashboards.

### Metrics

- Enable structured counters/timers with `ARTICLE_EXTRACTOR_METRICS_ENABLED=1`. Without further configuration, metrics fall back to the log sink and show up as JSON lines tagged with `metric_*` fields for scraping or `jq` piping.
- Set `ARTICLE_EXTRACTOR_METRICS_SINK=statsd` and provide `ARTICLE_EXTRACTOR_METRICS_STATSD_HOST/ARTICLE_EXTRACTOR_METRICS_STATSD_PORT` (typically `8125`) to stream the same counters to StatsD/DogStatsD. Use `ARTICLE_EXTRACTOR_METRICS_NAMESPACE=article_extractor` (or any prefix) to keep dashboards tidy.
- The FastAPI server records request totals and durations in middleware so every request can be tagged with `method`, `path`, `status`, and the coarse `status_group` bucket described in the [FastAPI middleware guide](https://fastapi.tiangolo.com/tutorial/middleware/) #techdocs fastapi.
- The CLI emits `cli_extractions_total`, `cli_extractions_failed_total`, and `cli_extraction_duration_ms` to track batch jobs by source (`url`, `file`, `stdin`) and output format.
- Metrics share the same `.env` loading rules as the rest of the settings, so a `.env` file can toggle log-formatting, diagnostics, and StatsD routing together.

Example: send request metrics to a local DogStatsD sidecar while still logging JSON:

```bash
ARTICLE_EXTRACTOR_METRICS_ENABLED=1 \
ARTICLE_EXTRACTOR_METRICS_SINK=statsd \
ARTICLE_EXTRACTOR_METRICS_STATSD_HOST=127.0.0.1 \
ARTICLE_EXTRACTOR_METRICS_STATSD_PORT=8125 \
ARTICLE_EXTRACTOR_METRICS_NAMESPACE=article_extractor \
uv run uvicorn article_extractor.server:app --port 3000
```

## Python API

```python
from article_extractor import extract_article, extract_article_from_url, ExtractionOptions

options = ExtractionOptions(min_word_count=120, include_images=True)
result = extract_article("<html>...</html>", url="https://example.com", options=options)

print(result.title)
print(result.excerpt)
print(result.success)
```

ArticleResult fields: `title`, `content`, `markdown`, `excerpt`, `word_count`, `success`, `error`, `url`, `author`, `date_published`, `language`, `warnings`.

## Use Cases

- LLM and RAG ingestion with clean Markdown ready for embeddings.
- Content archiving and doc syncing without ads or cruft.
- RSS/feed readers and knowledge tools that need readable HTML.
- Research pipelines that batch-extract large reading lists.

## How It Works

1. Parse HTML with [JustHTML](https://github.com/EmilStenstrom/justhtml).
2. Strip noise (scripts, nav, styles) and find content candidates.
3. Score candidates with a Readability-inspired model (density, link ratio, structure hints).
4. Pick the winner, normalise headings/links, and emit clean HTML.
5. Convert to GFM-compatible Markdown for downstream tools.

## Configuration

```bash
HOST=0.0.0.0
PORT=3000
WEB_CONCURRENCY=2
ARTICLE_EXTRACTOR_CACHE_SIZE=1000
ARTICLE_EXTRACTOR_THREADPOOL_SIZE=0
ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT=true
ARTICLE_EXTRACTOR_STORAGE_STATE_FILE=/data/storage-state.json  # alias for Playwright storage path
ARTICLE_EXTRACTOR_LOG_LEVEL=info
ARTICLE_EXTRACTOR_LOG_FORMAT=json
ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=0
ARTICLE_EXTRACTOR_METRICS_ENABLED=0
ARTICLE_EXTRACTOR_METRICS_SINK=log
# Define host/port when using StatsD
ARTICLE_EXTRACTOR_METRICS_STATSD_HOST=127.0.0.1
ARTICLE_EXTRACTOR_METRICS_STATSD_PORT=8125
ARTICLE_EXTRACTOR_METRICS_NAMESPACE=article_extractor
# Legacy equivalent (still supported):
# PLAYWRIGHT_STORAGE_STATE_FILE=/data/storage-state.json
```

### `.env` files everywhere

Both the CLI and FastAPI server load settings via
[`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/),
mirroring the pattern recommended in the
[FastAPI settings guide](https://fastapi.tiangolo.com/advanced/settings/).
Drop a `.env` file in your working directory and every `ARTICLE_EXTRACTOR_*`
variable will be read automatically without exporting shell env vars:

```
# .env
ARTICLE_EXTRACTOR_CACHE_SIZE=2000
ARTICLE_EXTRACTOR_THREADPOOL_SIZE=8
ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT=false
ARTICLE_EXTRACTOR_STORAGE_STATE_FILE=$HOME/.article-extractor/storage_state.json
ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=0
ARTICLE_EXTRACTOR_METRICS_ENABLED=1
ARTICLE_EXTRACTOR_METRICS_SINK=statsd
ARTICLE_EXTRACTOR_METRICS_STATSD_HOST=dogstatsd
ARTICLE_EXTRACTOR_METRICS_STATSD_PORT=8125
```

Environment variables still win over `.env` values, so CI/CD pipelines can
override local defaults without touching the file.

## Troubleshooting

- JavaScript-heavy sites: `pip install article-extractor[playwright]` and try again.
- Empty or short output: lower `min_word_count` or inspect `result.warnings`.
- Ports busy: `lsof -i :3000` then restart with `--port 8000`.

## Development

```bash
git clone https://github.com/pankaj28843/article-extractor.git
cd article-extractor
uv sync --all-extras
uv run ruff format . && uv run ruff check --fix .
uv run pytest tests/ -v
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, coding standards, and the full validation loop. PRs with tests and doc improvements are welcome.

## License

MIT — see [LICENSE](LICENSE)

## Acknowledgments

- [JustHTML](https://github.com/EmilStenstrom/justhtml) — HTML5 parser
- [Mozilla Readability.js](https://github.com/mozilla/readability) — Extraction algorithm
- [readability-js-server](https://github.com/phpdocker-io/readability-js-server) — API design inspiration
