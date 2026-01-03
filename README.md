# Article Extractor

[![PyPI version](https://img.shields.io/pypi/v/article-extractor.svg)](https://pypi.org/project/article-extractor/)
![Python versions](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml/badge.svg)](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pankaj28843/article-extractor/branch/main/graph/badge.svg)](https://codecov.io/gh/pankaj28843/article-extractor)

High-fidelity article extraction in pure Python: library, HTTP API, and CLI that turn messy web pages into clean Markdown or HTML for ingestion, archiving, and LLM pipelines.

> Requires Python 3.12+

## Audience & Prerequisites

- Backend, data, and tooling teams that need reliable article text for search, RAG, or analytics.
- Engineers who prefer a single-language stack with fast installs and reproducible results.
- Teams that want a ready-to-ship server/CLI and a composable Python API.

**Prerequisites**

- Python 3.12+ with `pip` or `uv` for the CLI/library flows
- Docker 24+ for the container/server quick start
- A network connection to fetch the target page (proxy-friendly; see networking section later)

Expect the CLI tutorial to reach first output in <2 minutes once dependencies are installed; server and Docker flows average ~5 minutes end-to-end.

## Quick Start (pick one)

Pick the flow that matches your environment. Each mini-tutorial highlights the time commitment, prerequisites, and the expected result so you can confirm success quickly.

### Tutorial: CLI in 2 minutes

**Time**: ~2 minutes once Python is installed  
**Prerequisites**: Python 3.12+, `pip` (or `uv pip`)  
**What you'll learn**: Run the CLI against a public URL and capture Markdown output

1. Install the package:

    ```bash
    pip install article-extractor
    ```

2. Extract from Wikipedia and print Markdown:

    ```bash
    article-extractor https://en.wikipedia.org/wiki/Wikipedia --output markdown
    ```

Successful runs echo the detected title, excerpt, and word count before streaming Markdown to stdout. If you hit proxy hurdles, skip down to the networking controls section.

### Tutorial: Server via Docker (5 minutes)

**Time**: ~5 minutes  
**Prerequisites**: Docker 24+, outbound network access  
**What you'll learn**: Launch the FastAPI server in a container and verify extraction through `curl`

1. Start the container:

    ```bash
    docker run -p 3000:3000 ghcr.io/pankaj28843/article-extractor:latest
    ```

2. POST a URL to the service:

    ```bash
    curl -XPOST http://localhost:3000/ \
        -H "Content-Type: application/json" \
        -d '{"url": "https://en.wikipedia.org/wiki/Wikipedia"}' | jq '.title, .word_count'
    ```

Look for HTTP 200 with title + word count in the JSON response. Use the Docker overrides section below if you want persistent storage or Playwright defaults.

### Tutorial: Python Library (5 minutes)

**Time**: ~5 minutes including install  
**Prerequisites**: Python 3.12+, ability to import from `src` or installed package  
**What you'll learn**: Call `extract_article()` directly inside your codebase

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

Expect `result.success` to be `True`; passing the `url` parameter improves scoring and warning metadata.

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

## Documentation Map

- **Tutorials**: Follow the [Quick Start](#quick-start-pick-one) paths or the [Docker smoke harness](#docker-smoke-harness) section to learn workflows end-to-end.
- **How-To Guides**: Use [Override cache + Playwright storage in Docker](#override-cache--playwright-storage-in-docker) and [Networking controls](#networking-controls-cli--server) when solving specific deployment tasks.
- **Reference**: Keep [Configuration](#configuration) and [Observability](#observability) handy for environment variables, metrics, and logging switches.
- **Explanation**: Read [Why Teams Choose Article Extractor](#why-teams-choose-article-extractor) and [How It Works](#how-it-works) for the rationale behind our scoring pipeline.

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

- Structured logs stream to stderr/stdout in JSON so Docker logging drivers and `journald` can parse them; flip to text with `--log-format text` or `ARTICLE_EXTRACTOR_LOG_FORMAT=text` when debugging locally.
- Control verbosity via `--log-level` (CLI default `critical`) or `ARTICLE_EXTRACTOR_LOG_LEVEL` (server default `INFO`).
- Sanitized URLs (`https://host/path`) prevent credential leakage; every response carries an `X-Request-ID` for trace correlation.
- Enable per-request diagnostics with `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1` (or CLI flag) to capture httpx retries, Playwright metadata, and queue stats.
- Point Docker logging to Fluent Bit/Fluentd/GELF using the [official logging driver switches](https://docs.docker.com/engine/logging/configure/) instead of duplicating collector configs here.

Example local triage session:

```bash
ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1 uv run article-extractor https://example.com
```

### Metrics

- Toggle metrics with `ARTICLE_EXTRACTOR_METRICS_ENABLED`. By default, counters are logged as JSON (`metric_*` fields) so you can scrape them with any log pipeline.
- Switch `ARTICLE_EXTRACTOR_METRICS_SINK` to `statsd` plus host/port env vars to emit the same counters (namespaced via `ARTICLE_EXTRACTOR_METRICS_NAMESPACE`).
- FastAPI middleware tracks request totals/durations; the CLI emits `cli_extractions_*` counters for URLs, files, and stdin sources.
- Configure the above via `.env` the same way you manage cache, logging, or storage settings—see the [Configuration](#configuration) table for canonical defaults.

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

### Playwright storage queue (shared cookies)

Headed Playwright runs now write session cookies through a durable queue so
multiple workers can share one `storage_state.json` without clobbering each
other. The queue lives beside the storage file (`storage_state.json.changes/` by
default) and replays the newest payload atomically after every request. Tune it
with the new environment variables:

- `ARTICLE_EXTRACTOR_STORAGE_QUEUE_DIR` — override the default
    `<storage_state>.changes` directory if you prefer a custom mount.
- `ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_ENTRIES` — CRITICAL log threshold when
    pending snapshots exceed this depth (default 20).
- `ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_AGE_SECONDS` — emits CRITICAL logs when
    the oldest pending snapshot stays queued longer than this many seconds
    (default 60s).
- `ARTICLE_EXTRACTOR_STORAGE_QUEUE_RETENTION_SECONDS` — how long processed
    change docs stick around for forensic analysis before being pruned (default
    300s).

Set these env vars (or `.env` keys) wherever you run the CLI/server so shared
Playwright state stays consistent across cron jobs, Docker containers, or
headed-debug sessions.

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

### Docker smoke harness (How-To)

**Goal**: Validate the Docker image plus Playwright storage queue end-to-end  
**Prerequisites**: Docker 24+, uv, and the optional `httpx` extra for the harness  
**Verification**: Harness exits 0 and logs `Docker validation harness completed successfully`

1. Run the harness (skip the rebuild during local edits):

        ```bash
        uv run scripts/debug_docker_deployment.py --skip-build --tail-lines 120
        ```

2. Inspect the final log tail for HTTP 200s and queue statistics. If a URL fails,
     rerun with `--retries 2` or point `--urls-file` at a custom corpus.

3. Need to tweak published settings? Pass env vars (e.g.,
     `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1`) directly through `uv run` and recheck the
     Playwright storage summary printed by the harness.

For the full flag list, run `uv run scripts/debug_docker_deployment.py --help`
and expect output similar to:

```text
$ uv run scripts/debug_docker_deployment.py --help
usage: debug_docker_deployment.py [-h] [--image-tag IMAGE_TAG] [...] [--health-timeout HEALTH_TIMEOUT]
Rebuild the Docker image, start the FastAPI service, and fire parallel smoke requests to validate Playwright storage behavior.
options:
    -h, --help            show this help message and exit
    --image-tag IMAGE_TAG Docker image tag to build/run.
    --container-name CONTAINER_NAME
                                         Name of the temporary Docker container.
    ... (run the command for the complete list)
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, coding standards, and the full validation loop. PRs with tests and doc improvements are welcome.

## License

MIT — see [LICENSE](LICENSE)

## Acknowledgments

- [JustHTML](https://github.com/EmilStenstrom/justhtml) — HTML5 parser
- [Mozilla Readability.js](https://github.com/mozilla/readability) — Extraction algorithm
- [readability-js-server](https://github.com/phpdocker-io/readability-js-server) — API design inspiration
