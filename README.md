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
LOG_LEVEL=info
WEB_CONCURRENCY=2
ARTICLE_EXTRACTOR_CACHE_SIZE=1000
ARTICLE_EXTRACTOR_THREADPOOL_SIZE=0
```

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
