# Article Extractor

[![PyPI version](https://img.shields.io/pypi/v/article-extractor.svg)](https://pypi.org/project/article-extractor/)
![Python versions](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml/badge.svg)](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pankaj28843/article-extractor/branch/main/graph/badge.svg)](https://codecov.io/gh/pankaj28843/article-extractor)

High-fidelity article extraction in pure Python. Ship the same scoring engine as a library, CLI, or FastAPI service to turn messy web pages into clean Markdown or HTML for ingestion, archiving, and LLM pipelines.

> Requires Python 3.12+

## Value At a Glance

- Deterministic Readability-style scoring tuned for long-form docs, blogs, and knowledge bases.
- Clean, GFM-compatible Markdown and sanitized HTML identical across CLI, server, and Python API.
- Production-ready knobs: persistent Playwright storage, cache sizing, proxy & diagnostics controls, and StatsD metrics.
- High-coverage test suite (>93%) and GitHub Pages docs with reality-checked commands.

Learn why teams adopt the extractor in [Why Teams Choose Article Extractor](https://pankaj28843.github.io/article-extractor/explanations/why/) and how the heuristics work in [How It Works](https://pankaj28843.github.io/article-extractor/explanations/how-it-works/).

## Choose Your Surface

| Goal | Start Here | Time | Verified Commands |
| --- | --- | --- | --- |
| Run the CLI once | [Tutorial: CLI in 2 Minutes](https://pankaj28843.github.io/article-extractor/tutorials/cli/) | < 2 min | `uv pip install article-extractor`, `uv run article-extractor …` |
| Ship the FastAPI server in Docker | [Tutorial: Docker in 5 Minutes](https://pankaj28843.github.io/article-extractor/tutorials/docker/) | ~5 min | `docker run ghcr.io/pankaj28843/article-extractor:latest`, `curl http://localhost:3000/` |
| Embed the library | [Tutorial: Python in 5 Minutes](https://pankaj28843.github.io/article-extractor/tutorials/python/) | ~5 min | `uv run python demo.py` |
| Tune caches, storage, proxies, diagnostics | [How-To Guides](https://pankaj28843.github.io/article-extractor/how-to/) | task-specific | Env vars & CLI/server overrides |

See the [Documentation Coverage Map](https://pankaj28843.github.io/article-extractor/coverage-map/) for a MECE index of every page.

## Install (Any Environment)

```bash
pip install article-extractor           # CLI + library
pip install article-extractor[server]   # FastAPI server extras
pip install article-extractor[all]      # Playwright, httpx, FastAPI, fake-useragent
```

Prefer uv? Run `uv pip install article-extractor` or add it to `pyproject.toml` via `uv add article-extractor[all]`.

## Observability & Operations

- All runtimes honor diagnostics toggles (`ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS`, `ARTICLE_EXTRACTOR_METRICS_*`).
- Docker image ships Chromium + Playwright state persistence. Follow [How-To: Cache & Playwright Storage](https://pankaj28843.github.io/article-extractor/how-to/cache-playwright/) for overrides.
- Metrics and logging recipes live in [How-To: Diagnostics & Metrics](https://pankaj28843.github.io/article-extractor/how-to/diagnostics/).

## Documentation

The full MkDocs site (Tutorials, How-To, Reference, Explanations, Contributing, Release) lives at **https://pankaj28843.github.io/article-extractor/**. If the site is unavailable, read the Markdown sources in [`docs/`](docs/).

## Contributing

We welcome pull requests paired with docs. Start with the [Docs Contribution Guide](https://pankaj28843.github.io/article-extractor/contributing/), follow the [Development Workflow](https://pankaj28843.github.io/article-extractor/contributing/development/), and verify commands via the docsRealityCheck checklist before opening a PR.

## License

MIT — see [LICENSE](LICENSE).
