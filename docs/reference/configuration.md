# Configuration Table

**Audience & Prereqs**: Operators in the Reference lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table) who need authoritative settings without walkthrough context; arrive familiar with the CLI/server surfaces.  
**Usage**: Copy these values into `.env`, Docker, or CI pipelines; pair with the related How-To guide for procedural steps.

Environment variables and `.env` keys that control Article Extractor in every runtime. Values marked with *default* mirror the ones defined in code and shipped containers.

## Core Settings

| Setting | Default | Applies To | Description |
| --- | --- | --- | --- |
| `HOST` | `0.0.0.0` | Server | Bind address for FastAPI/uvicorn. |
| `PORT` | `3000` | Server | HTTP port for the FastAPI app. |
| `WEB_CONCURRENCY` | `2` | Server | Gunicorn/uvicorn worker count inside Docker. |
| `ARTICLE_EXTRACTOR_CACHE_SIZE` | `1000` | All | LRU cache entries for rendered articles. Increase for reuse-heavy workloads. |
| `ARTICLE_EXTRACTOR_THREADPOOL_SIZE` | `0` | All | Worker threads for CPU-bound tasks. `0` lets Python choose. |
| `ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT` | `true` when Playwright installed | All | Choose Playwright over httpx when both exist. Mirrors CLI `--prefer-*` flags. |
| `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE` | (unset) | All | Path to persistent Playwright cookies; alias for `PLAYWRIGHT_STORAGE_STATE_FILE`. |
| `ARTICLE_EXTRACTOR_LOG_LEVEL` | `info` (server) / `critical` (CLI) | All | Log verbosity. |
| `ARTICLE_EXTRACTOR_LOG_FORMAT` | `json` | All | `json` or `text`. |
| `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS` | `0` | All | Emit retry/cache metadata when set to `1`. |
| `ARTICLE_EXTRACTOR_METRICS_ENABLED` | `0` | All | Toggle metrics. |
| `ARTICLE_EXTRACTOR_METRICS_SINK` | `log` | All | `log` or `statsd`. |
| `ARTICLE_EXTRACTOR_METRICS_STATSD_HOST` | `127.0.0.1` | StatsD sink | Destination host. |
| `ARTICLE_EXTRACTOR_METRICS_STATSD_PORT` | `8125` | StatsD sink | Destination port. |
| `ARTICLE_EXTRACTOR_METRICS_NAMESPACE` | `article_extractor` | StatsD sink | Metric prefix. |
| `ARTICLE_EXTRACTOR_STORAGE_QUEUE_DIR` | `<storage_state>.changes` | Playwright | Directory that stores staged cookie snapshots. |
| `ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_ENTRIES` | `20` | Playwright | Emit CRITICAL logs when pending entries exceed this number. |
| `ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_AGE_SECONDS` | `60` | Playwright | Emit CRITICAL logs when the oldest pending snapshot exceeds this age. |
| `ARTICLE_EXTRACTOR_STORAGE_QUEUE_RETENTION_SECONDS` | `300` | Playwright | Keep processed snapshots for this duration before pruning. |

## Proxy & Networking

- `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` follow the [Networking Controls guide](../how-to/networking.md).
- CLI flags override these values per invocation.

## Observability Settings

- `ARTICLE_EXTRACTOR_LOG_LEVEL`, `ARTICLE_EXTRACTOR_LOG_FORMAT`, and `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS` stay active in every runtime so you can dial verbosity up without redeploying. Combine them with `uv run article-extractor --log-format text` when debugging locally.
- Metrics live behind `ARTICLE_EXTRACTOR_METRICS_ENABLED`. Set it to `1` and point `ARTICLE_EXTRACTOR_METRICS_SINK=statsd` plus the `STATSD_*` knobs to emit counters/timers to an upstream collector.
- The FastAPI server exposes the same switches through its JSON body; see [Diagnostics & Observability](../how-to/diagnostics.md) for a walkthrough that captures sample output and log snippets.

## `.env` Files Everywhere

Both the CLI and FastAPI server load settings via [`pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/), matching FastAPI’s recommended approach (#techdocs https://fastapi.tiangolo.com/advanced/settings/). Drop a `.env` file next to your entrypoint and every `ARTICLE_EXTRACTOR_*` variable will be read automatically:

```
# .env example
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

Environment variables override `.env` entries so CI/CD systems can replace local defaults without modifying the file.

## Playwright Storage Queue

Headed Playwright runs write session data through a durable queue that lives next to the storage file. Keep the queue on the same mounted volume and tune the thresholds listed above so multiple workers can safely share cookies.

Refer to [Override Cache & Playwright Storage](../how-to/cache-playwright.md) for an end-to-end walkthrough.
