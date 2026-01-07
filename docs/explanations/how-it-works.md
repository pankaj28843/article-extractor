# How It Works

This page summarizes how parsing, scoring, fetchers, and observability fit together so contributors can reason about the system before editing code or docs.

**Audience**: Contributors and operators who want the architecture overview.  
**Prerequisites**: Basic familiarity with HTML parsing and async I/O.  
**Time**: ~10 minutes.  
**What you'll learn**: How parsing, scoring, fetchers, and observability connect.

## Deterministic Pipeline

1. **Parse HTML** with [JustHTML](https://github.com/EmilStenstrom/justhtml) inside `extractor.py`, stripping script/nav noise before candidate scoring.
2. **Score blocks** using Readability-style signals (density, link ratio, heading boosts). Intuitively, $$density = \frac{text\_length}{node\_area}$$ favors long paragraphs inside narrow containers.
3. **Select the winner**, normalize headings/links, and emit sanitized HTML + Markdown plus metadata (`title`, `excerpt`, `warnings`, `word_count`).
4. **Reuse fetchers** by funneling every CLI/server/Python request through `FetchPreferences`, which picks Playwright or httpx deterministically based on installed extras and per-request overrides.

## Boundaries & Storage

- `extractor.py` owns candidate scoring; `fetcher.py` and `network.py` own HTTP/Playwright orchestration; `server.py` stays thin and only parses environment variables into typed settings (see `.github/instructions/software-engineering-principles.instructions.md`).
- When you opt in via `--storage-state`/`ARTICLE_EXTRACTOR_STORAGE_STATE_FILE`, headed Playwright sessions persist cookies to `storage_state.json` and queue deltas beside the file so multiple workers share authenticated sessions without race conditions. Leave the setting unset for the default ephemeral behavior, and tune the queue thresholds listed in the [Reference](../reference.md#configuration) when logs warn about pending entries or stale snapshots.

## Observability

- Structured logs expose `request_id`, latency, fetcher choice, cache hits, and queue depth; enable them via `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1` and the log level/format env vars documented in the [Operations Runbook](../operations.md#diagnostics-and-metrics).
- Optional StatsD metrics (`article_extractor.cli_extractions.success`, `article_extractor.server.latency_ms`) stream when `ARTICLE_EXTRACTOR_METRICS_ENABLED=1` with `metrics_sink=statsd`.

When you need runnable instructions, jump back to the [Tutorials](../tutorials.md) and [Operations](../operations.md) pages—the pipeline above explains why those commands behave the way they do.
