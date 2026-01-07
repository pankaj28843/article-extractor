# Reference

One lookup table consolidates the runtime settings plus canonical CLI, FastAPI, and library entrypoints so you can grab the exact knob that matters mid-incident.

**Audience**: Operators and developers needing exact settings or command syntax.  
**Prerequisites**: Familiarity with CLI flags or server env vars.  
**Time**: ~5 minutes to find a specific setting.  
**What you'll learn**: Defaults, overrides, and the canonical entrypoints.

## Configuration

| Setting | Default | Applies To | Description |
| --- | --- | --- | --- |
| `HOST` | `0.0.0.0` | Server | Bind address for uvicorn/gunicorn. |
| `PORT` | `3000` | Server | FastAPI HTTP port. |
| `WEB_CONCURRENCY` | `2` | Server | Worker count inside the Docker image. |
| `ARTICLE_EXTRACTOR_CACHE_SIZE` | `1000` | All | LRU entries for rendered articles; raise for reuse-heavy corpora. |
| `ARTICLE_EXTRACTOR_THREADPOOL_SIZE` | `0` | All | Worker threads for CPU-heavy steps; `0` lets Python choose. |
| `ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT` | `true` when Playwright exists | All | Force Playwright over httpx when both are available. Mirrors CLI flags. |
| `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE` | unset | All | Optional path to persist Chromium cookies (`/data/storage_state.json` in Docker examples). Leave unset for the default ephemeral session. |
| `ARTICLE_EXTRACTOR_STORAGE_QUEUE_DIR` | `<storage_state>.changes` | Playwright | Directory for queued deltas when persistence is enabled; keep it on the same mount as the storage file. |
| `ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_ENTRIES` | `20` | Playwright | Warn when pending deltas exceed this count. |
| `ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_AGE_SECONDS` | `60` | Playwright | Warn when the oldest pending delta lives longer than this age. |
| `ARTICLE_EXTRACTOR_STORAGE_QUEUE_RETENTION_SECONDS` | `300` | Playwright | Retain processed deltas for this many seconds before pruning. |
| `ARTICLE_EXTRACTOR_LOG_LEVEL` | `info` (server) / `critical` (CLI) | All | Set to `debug`, `info`, `warning`, etc. |
| `ARTICLE_EXTRACTOR_LOG_FORMAT` | `json` | All | `json` or `text`. |
| `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS` | `0` | All | Emit cache/fetch metadata when set to `1`. |
| `ARTICLE_EXTRACTOR_METRICS_ENABLED` | `0` | All | Toggle metrics emission. |
| `ARTICLE_EXTRACTOR_METRICS_SINK` | `log` | All | `log` or `statsd`. |
| `ARTICLE_EXTRACTOR_METRICS_STATSD_HOST` | `127.0.0.1` | StatsD | Destination host. |
| `ARTICLE_EXTRACTOR_METRICS_STATSD_PORT` | `8125` | StatsD | Destination port. |
| `ARTICLE_EXTRACTOR_METRICS_NAMESPACE` | `article_extractor` | StatsD | Metric prefix used in counters/timers. |
| `ARTICLE_EXTRACTOR_CRAWLER_CONCURRENCY` | `5` | Crawler | Default concurrent requests for crawl jobs. |
| `ARTICLE_EXTRACTOR_CRAWLER_RATE_LIMIT` | `1.0` | Crawler | Default seconds between requests to same host. |
| `ARTICLE_EXTRACTOR_CRAWLER_MAX_PAGES` | `100` | Crawler | Default page limit for crawl jobs. |

## `.env` and precedence

Both the CLI and FastAPI server load settings via `pydantic-settings`. Drop a `.env` file next to your entrypoint and every `ARTICLE_EXTRACTOR_*` variable will be loaded automatically; explicit environment variables override `.env` entries so CI/CD can replace local defaults without touching the file.

```ini
# .env example
ARTICLE_EXTRACTOR_CACHE_SIZE=2000
ARTICLE_EXTRACTOR_THREADPOOL_SIZE=8
ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT=false
# Uncomment when you intentionally persist Playwright storage
# ARTICLE_EXTRACTOR_STORAGE_STATE_FILE=$HOME/.article-extractor/storage_state.json
ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=0
ARTICLE_EXTRACTOR_METRICS_ENABLED=1
ARTICLE_EXTRACTOR_METRICS_SINK=statsd
ARTICLE_EXTRACTOR_METRICS_STATSD_HOST=dogstatsd
ARTICLE_EXTRACTOR_METRICS_STATSD_PORT=8125
```

## Runtime Interfaces

### CLI

```bash
# Markdown output
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia --output markdown

# Local HTML file
uv run article-extractor --file article.html --output markdown

# Diagnostics + Playwright
ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1 \
uv run article-extractor https://example.com --prefer-playwright --headed --user-interaction-timeout 30
```

Highlight flags:
- `--output` (`json`, `markdown`, `text`)
- `--min-words`, `--no-images`, `--no-code`
- `--user-agent`, `--random-user-agent`
- `--proxy`, `--prefer-playwright`, `--prefer-httpx`
- `--headed`, `--storage-state`
- `--log-level`, `--log-format`

Run `uv run article-extractor --help` after each pull; CI and the validation loop ensure help text stays accurate.

### FastAPI

```bash
uv run uvicorn article_extractor.server:app --host 0.0.0.0 --port 3000
```

Endpoints:
- `POST /` — `{"url": "…", "prefer_playwright": false, "network": {…}}`
- `POST /crawl` — Submit crawl job `{"output_dir": "…", "seeds": […], "max_pages": 100}`
- `GET /crawl/{job_id}` — Poll crawl job status
- `GET /crawl/{job_id}/manifest` — Download manifest.json when complete
- `GET /health` — readiness probe used in tutorials and Docker harnesses
- `GET /docs` — interactive OpenAPI UI (served by FastAPI)

Every JSON field maps to `FetchPreferences` / `NetworkOptions`; see the [Crawling](crawling.md) guide for batch extraction or the [Networking Controls](operations.md#networking-controls) recipe for a runnable example.

### Python API

```python
from article_extractor import (
    extract_article,
    extract_article_from_url,
    ExtractionOptions,
)

options = ExtractionOptions(min_word_count=120, include_images=True)
result = extract_article("<html>…</html>", url="https://example.com", options=options)
print(result.title, result.word_count)
```

Use `await extract_article_from_url("https://example.com")` (or the helper shown in the tutorials) inside async frameworks. Pass `network=NetworkOptions(...)` to keep proxies, storage state, and headed mode consistent with CLI/server behavior.

## Transient 404 Handling

Modern SPAs sometimes return HTTP 404 from the origin server while JavaScript renders real article content client-side. The extractor handles this automatically:

1. **Transient status detection** — When a fetch returns 404 or 410, the extractor inspects the HTML before failing. If the response contains `<article>`, `<main>`, or paragraph tags and exceeds 500 bytes, extraction proceeds.
2. **Warning annotation** — Successful extraction from a 404 response appends a warning like `"Extracted after HTTP 404 (SPA/client-rendered)"` to `ArticleResult.warnings`.
3. **httpx → Playwright fallback** — When `--prefer-httpx` is active and httpx returns a transient 404, the extractor automatically retries with Playwright (if installed) before giving up. This captures pages that need JavaScript execution.

Check `result.warnings` for transparency; the warning signals that the HTTP status was non-2xx but content was still usable.

## Observability quick reference

- Diagnostics toggles: `ARTICLE_EXTRACTOR_LOG_LEVEL`, `ARTICLE_EXTRACTOR_LOG_FORMAT`, `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS`.
- Metrics: enable via `ARTICLE_EXTRACTOR_METRICS_ENABLED=1`, pick `log` or `statsd` sinks, then configure host/port/namespace.
- Storage queue: monitor logs for `storage_queue_pending_entries` and increase the thresholds documented above when sharing Playwright state across workers.

Pair every setting here with the verification steps in the [Operations Runbook](operations.md) so the commands and defaults stay in sync.
