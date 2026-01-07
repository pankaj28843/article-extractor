# Article Extractor

[![PyPI version](https://img.shields.io/pypi/v/article-extractor.svg)](https://pypi.org/project/article-extractor/)
![Python versions](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml/badge.svg)](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pankaj28843/article-extractor/branch/main/graph/badge.svg)](https://codecov.io/gh/pankaj28843/article-extractor)

Article Extractor turns arbitrary HTML into deterministic Markdown ready for ingestion pipelines.

> **Problem**: brittle scrapers collapse when paywalls or inline scripts mutate markup.  \
> **Why now**: one fetcher abstraction keeps Playwright and httpx output identical across the CLI, FastAPI server, and Python API.  \
> **Outcome**: verified tutorials, a single operations runbook, and concise reference tables keep teams unblocked in production.

**Audience**: Engineers shipping ingestion pipelines, doc search, or automation that needs stable Markdown from HTML.

**Prerequisites**: Python 3.12+ (optional: `uv` for tooling, Docker for server demos).

**Time**: 2–10 minutes depending on whether you use CLI, server, or library.

**What you'll learn**: How to run the CLI once, start the FastAPI server, or embed the library in your app.

## Value At a Glance

- Deterministic Readability-style scoring tuned for long-form docs, blogs, and knowledge bases.
- GFM-compatible Markdown and sanitized HTML identical across the CLI, FastAPI server, and Python API.
- Runtime knobs for Playwright storage, cache sizing, proxies, diagnostics, and StatsD metrics.
- Test suite coverage above 93% plus documentation that records the exact commands and outputs.

See the [Docs Home](https://pankaj28843.github.io/article-extractor/) for the consolidated Tutorials, Operations, Reference, and Style sections.

## Choose Your Surface

| Goal | Start Here | Time | Verified Commands |
| --- | --- | --- | --- |
| Run the CLI once | [CLI Fast Path](https://pankaj28843.github.io/article-extractor/tutorials/#cli-fast-path) | < 2 min | `uv pip install article-extractor`, `uv run article-extractor …`, `head ./tmp/article-extractor-cli.md` |
| Ship the FastAPI server in Docker | [Docker Service](https://pankaj28843.github.io/article-extractor/tutorials/#docker-service) | ~5 min | `docker run ghcr.io/pankaj28843/article-extractor:latest`, `curl http://localhost:3000/health`, `curl -XPOST … | jq` |
| Embed the library | [Python Embedding](https://pankaj28843.github.io/article-extractor/tutorials/#python-embedding) | ~5 min | `uv run python - <<'PY' …`, `asyncio.run(fetch_remote())` |
| Tune caches, networking, diagnostics, releases | [Operations Runbook](https://pankaj28843.github.io/article-extractor/operations/) | task-specific | Env vars, Docker overrides, StatsD flags, `gh` CLI |

## Install (Any Environment)

```bash
pip install article-extractor           # CLI + library
pip install article-extractor[server]   # FastAPI server extras
pip install article-extractor[all]      # Playwright, httpx, FastAPI, fake-useragent
```

Prefer uv? Run `uv pip install article-extractor` or add it to `pyproject.toml` via `uv add article-extractor[all]`.

### Developer / Active Development Install

When contributing or debugging locally, install as an editable tool so changes to `src/` take effect immediately:

```bash
# Clone and install editable
git clone https://github.com/pankaj28843/article-extractor.git
cd article-extractor
uv tool install --editable --force --refresh --reinstall ".[all]"

# Now `article-extractor` CLI reflects local changes instantly
article-extractor https://example.com
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development workflow.

## Crawl an Entire Site

Extract every page under a domain in one command:

```bash
# CLI: crawl up to 50 pages, output to ./output/
uv run article-extractor crawl https://example.com --max-pages 50 --output ./output

# Server: start a background crawl job
curl -X POST http://localhost:3000/crawl \
  -H "Content-Type: application/json" \
  -d '{"start_url": "https://example.com", "max_pages": 50}'
# Returns {"job_id": "abc123", "status": "running", ...}
```

The crawler follows internal links via BFS, respects `robots.txt` and sitemaps, and writes one Markdown file per page. Use `--workers 3` (default is 1) to dispatch three concurrent crawl workers while `--concurrency` continues to cap simultaneous fetch slots. See the [Crawling Guide](https://pankaj28843.github.io/article-extractor/crawling/) for rate limiting, headed mode, and output structure.

## Observability & Operations

- All runtimes honor diagnostics toggles (`ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS`, `ARTICLE_EXTRACTOR_METRICS_*`).
- Playwright storage is opt-in: CLI/server runs stay ephemeral unless you pass `--storage-state /path/to/storage_state.json` or set `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE` plus a bind-mounted volume. The [Operations Runbook](https://pankaj28843.github.io/article-extractor/operations/#cache-and-playwright-storage) walks through mounting, warming caches, and inspecting the queue.
- The Docker debug harness still exercises persistent storage for regression coverage; add `--disable-storage` when you want the smoke to mirror the default ephemeral behavior.
- Networking, diagnostics, StatsD, validation loops, and release automation live in a single [Operations Runbook](https://pankaj28843.github.io/article-extractor/operations/).

## Documentation

The MkDocs site (Overview, Tutorials, Operations, Reference, Explanations) lives at **https://pankaj28843.github.io/article-extractor/**. If the site is unavailable, read the Markdown sources in [`docs/`](docs/) including `style-guide.md`, `operations.md`, and `content-inventory.md`.

## Contributing

We welcome pull requests paired with docs. Follow the [Operations Runbook](https://pankaj28843.github.io/article-extractor/operations/#development-workflow-and-validation) for validation and include real command output in the PR description when you update documentation.

## License

MIT — see [LICENSE](LICENSE).
