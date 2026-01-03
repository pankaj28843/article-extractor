# Diagnostics & Metrics

**Audience & Prereqs**: Operators/devs in the How-To lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table); ensure a working CLI/server, optional StatsD endpoint, and (for Playwright logs) the `[all]` extra + `playwright install`.  
**Goal**: Enable verbose logging, capture sample diagnostics, and wire up log/StatsD sinks.

## 1. Enable Diagnostic Logs (CLI)

Turn on diagnostics and JSON logs for one command:

```bash
ARTICLE_EXTRACTOR_LOG_LEVEL=info \
ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1 \
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia --output text 2>&1 | head -n 10
```

Sample output (2026-01-03):

```text
{"timestamp": "2026-01-03T14:22:06.190498+00:00", "component": "cli", "message": "Extracting article", ...}
{"timestamp": "2026-01-03T14:22:06.775552+00:00", "message": "Playwright storage state", "storage_state": "/home/pankaj/.article-extractor/storage_state.json"}
{"timestamp": "2026-01-03T14:22:09.194603+00:00", "message": "Fetched with Playwright", "status_code": 200, "content_length": 1520863}
```

Set `ARTICLE_EXTRACTOR_LOG_FORMAT=text` if you prefer human-readable logs while pairing them with `tee` or your log agent.

## 2. Enable Diagnostics in Docker / Server

```bash
docker run --rm -d -p 3000:3000 --name article-extractor-diag \
  -e ARTICLE_EXTRACTOR_LOG_LEVEL=info \
  -e ARTICLE_EXTRACTOR_LOG_FORMAT=json \
  -e ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1 \
  ghcr.io/pankaj28843/article-extractor:latest

docker logs -f article-extractor-diag
```

Streamed logs include request IDs, cache hits, queue stats, and whether Playwright storage was reused. Stop the container with `docker stop article-extractor-diag` when you’re finished.

## 3. Metrics Sinks

### Log Sink (default)

Counters and timers appear inline with diagnostics logs (fields prefixed with `metric_`). Scrape them with your log pipeline or `jq`.

### StatsD Sink

```bash
export ARTICLE_EXTRACTOR_METRICS_ENABLED=1
export ARTICLE_EXTRACTOR_METRICS_SINK=statsd
export ARTICLE_EXTRACTOR_METRICS_STATSD_HOST=127.0.0.1
export ARTICLE_EXTRACTOR_METRICS_STATSD_PORT=8125
export ARTICLE_EXTRACTOR_METRICS_NAMESPACE=article_extractor
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia
```

Point `*_HOST/PORT` at your Datadog/Graphite agent. CLI runs emit `article_extractor.cli_extractions.success` counters; the FastAPI middleware reports HTTP durations.

## Verification Checklist

- Diagnostics logs contain `request_id`, fetcher name, and storage-path metadata for each request.
- Turning `ARTICLE_EXTRACTOR_METRICS_ENABLED=1` produces counter lines (log sink) or UDP packets (StatsD). Switching it back to `0` silences them.
- Docker/server logs show the JSON diagnostics banner when env vars above are set.

## Troubleshooting

- **Missing diagnostics**: Ensure `ARTICLE_EXTRACTOR_LOG_LEVEL` is `info` or lower; `warning` suppresses debug lines even when `LOG_DIAGNOSTICS=1`.
- **StatsD dropped packets**: Run `tcpdump -i lo udp port 8125` to confirm datagrams arrive; bump `ARTICLE_EXTRACTOR_METRICS_SAMPLE_RATE` only if needed.
- **Too chatty logs**: Reset `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=0` (default) and drop to `LOG_LEVEL=warning` outside of incidents.

## Related Docs

- [Configuration Reference](../reference/configuration.md#observability-settings) lists every observability toggle.
- [Release Engineering](../release-engineering/index.md#fastapi-health-check) pairs diagnostics with health checks before shipping.
