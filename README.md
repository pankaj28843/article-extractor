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

## Observability & Operations

- All runtimes honor diagnostics toggles (`ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS`, `ARTICLE_EXTRACTOR_METRICS_*`).
- Docker image ships Chromium + Playwright state persistence; the [Operations Runbook](https://pankaj28843.github.io/article-extractor/operations/#cache-and-playwright-storage) shows how to mount storage, warm caches, and inspect the queue.
- Networking, diagnostics, StatsD, validation loops, and release automation live in a single [Operations Runbook](https://pankaj28843.github.io/article-extractor/operations/).

## Documentation

The MkDocs site (Overview, Tutorials, Operations, Reference, Explanations) lives at **https://pankaj28843.github.io/article-extractor/**. If the site is unavailable, read the Markdown sources in [`docs/`](docs/) including `style-guide.md`, `operations.md`, and `content-inventory.md`.

## Contributing

We welcome pull requests paired with docs. Follow the [Operations Runbook](https://pankaj28843.github.io/article-extractor/operations/#development-workflow-and-validation) for validation, skim the [Style Guide](https://pankaj28843.github.io/article-extractor/style-guide/) before editing prose, and document real command output via the DocsRealityCheck log in `notes.md`.

## License

MIT — see [LICENSE](LICENSE).
