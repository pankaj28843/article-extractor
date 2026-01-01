# Article Extractor

[![PyPI version](https://img.shields.io/pypi/v/article-extractor.svg)](https://pypi.org/project/article-extractor/)
![Python versions](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml/badge.svg)](https://github.com/pankaj28843/article-extractor/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pankaj28843/article-extractor/branch/main/graph/badge.svg)](https://codecov.io/gh/pankaj28843/article-extractor)

**Pure-Python article extraction—extract clean content from any web page, no Node.js required.**

Article Extractor provides a **Python library**, **HTTP API server**, and **CLI tool** for extracting main content from HTML documents (articles, blog posts, documentation) and converting it to clean Markdown or HTML.

> **Requires Python 3.12+**

## Audience & Requirements

- **Built for** backend engineers, data teams, and tool builders who need high-quality article text for ingestion, summarization, or archiving.
- **You should be comfortable with** running CLI commands and basic Python packaging (`pip`, `uv`, or Docker).
- **No front-end or Node.js stack needed**; everything runs on CPython 3.12+.

## Documentation Map

1. [Why Article Extractor?](#why-article-extractor) – value proposition and differentiators.
2. [Installation](#installation) – Python package and `uv` instructions.
3. [Quick Start](#quick-start) – run it via server, CLI, or Docker in under five minutes.
4. [API Reference](#api-reference) – HTTP endpoints and Python helpers.
5. [Configuration](#configuration) – environment variables and deployment knobs.
6. [FAQ](#faq) & [Troubleshooting](#troubleshooting) – common questions and fixes.

## Why Article Extractor?

- **Pure Python** – No Node.js, no Selenium, no external APIs
- **Battle-tested** – Uses Mozilla Readability.js scoring algorithms
- **Markdown output** – Clean GFM for LLMs, docs, or archiving
- **Fast** – Cached calculations, early termination, 50-150ms typical extraction
- **Safe** – XSS-safe output via [JustHTML](https://github.com/EmilStenstrom/justhtml)
- **Flexible** – Library, HTTP server, or CLI
- **Well-tested** – 94%+ test coverage with comprehensive test suite

## Installation

```bash
pip install article-extractor[server]  # HTTP server
pip install article-extractor[all]     # All features

# Or with uv (faster)
uv add article-extractor --extra server
```

## Quick Start

> Prerequisites: Python 3.12+, `pip` (or `uv`), and optionally Docker if you prefer containers.

### As an HTTP Server

```bash
# Run in foreground
docker run -p 3000:3000 ghcr.io/pankaj28843/article-extractor:latest

# Run in daemon mode (detached)
docker run -d -p 3000:3000 --name article-extractor ghcr.io/pankaj28843/article-extractor:latest

# Or run locally with uvicorn
uvicorn article_extractor.server:app --host 0.0.0.0 --port 3000
```

**Extract from URL:**

```bash
curl -XPOST http://localhost:3000/ \
    -H "Content-Type: application/json" \
    -d'{"url": "https://en.wikipedia.org/wiki/Wikipedia"}'
```

**Response:**

```json
{
  "url": "https://en.wikipedia.org/wiki/Wikipedia",
  "title": "Wikipedia - Wikipedia",
  "byline": null,
  "dir": "ltr",
  "content": "<div><p>Wikipedia is a free content online encyclopedia...</p></div>",
  "length": 89234,
  "excerpt": "Wikipedia is a free content online encyclopedia written and maintained by a community of volunteers, known as Wikipedians, through open collaboration and using a wiki-based editing system called MediaWiki.",
  "siteName": null,
  "markdown": "# Wikipedia\n\nWikipedia is a free content online encyclopedia...",
  "word_count": 33414,
  "success": true
}
```

### As a CLI Tool

```bash
# Extract from URL
article-extractor https://en.wikipedia.org/wiki/Wikipedia

# Extract from file
article-extractor --file article.html --output markdown

# Extract from stdin
echo '<html>...</html>' | article-extractor --output text

# Or via Docker
docker run --rm -it ghcr.io/pankaj28843/article-extractor:latest \
    article-extractor https://en.wikipedia.org/wiki/Wikipedia
```

### As a Python Library

```python
from article_extractor import extract_article, extract_article_from_url
import asyncio

# From HTML string
html = '<html><body><article><h1>Title</h1><p>Content...</p></article></body></html>'
result = extract_article(html, url="https://en.wikipedia.org/wiki/Wikipedia")
print(result.markdown)
print(f"Extracted {result.word_count} words")

# From URL (async) - recommended for web pages
async def extract():
    result = await extract_article_from_url("https://en.wikipedia.org/wiki/Wikipedia")
    if result.success:
        print(f"Title: {result.title}")
        print(f"Words: {result.word_count}")
        print(f"Excerpt: {result.excerpt[:100]}...")
    else:
        print(f"Extraction failed: {result.error}")

asyncio.run(extract())
```

## Docker Usage

```bash
# Run in daemon mode
docker run -d -p 3000:3000 --name article-extractor \
    --restart unless-stopped \
    ghcr.io/pankaj28843/article-extractor:latest

# Check logs
docker logs article-extractor

# Stop/start/restart
docker stop article-extractor
docker start article-extractor
docker restart article-extractor

# CLI mode (one-off extraction)
docker run --rm ghcr.io/pankaj28843/article-extractor:latest \
    article-extractor https://en.wikipedia.org/wiki/Wikipedia --output markdown
```

**With docker-compose:**

```yaml
services:
  article-extractor:
    image: ghcr.io/pankaj28843/article-extractor:latest
    ports:
      - "3000:3000"
    restart: unless-stopped
    environment:
      - LOG_LEVEL=info
```

**Test the server:**

```bash
# Health check
curl http://localhost:3000/health

# Extract article
curl -XPOST http://localhost:3000/ \
    -H "Content-Type: application/json" \
    -d'{"url": "https://en.wikipedia.org/wiki/Wikipedia"}' | jq '.title'
```

**Supported platforms:** `linux/amd64`, `linux/arm64`  
**Available tags:** `latest`, `0`, `0.2`, `0.2.1`

## API Reference

### HTTP Endpoints

- `POST /` – Extract article (send `{"url": "..."}`)
- `GET /` – Service info
- `GET /health` – Health check  
- `GET /docs` – Interactive API docs

### Python API

```python
extract_article(html, url="", options=None) -> ArticleResult
extract_article_from_url(url, fetcher=None, options=None) -> ArticleResult
```

**ArticleResult fields:**
- `title` – Extracted article title
- `content` – Clean HTML content
- `markdown` – Markdown version (GFM-compatible)
- `excerpt` – First ~200 characters
- `word_count` – Total words in article
- `success` – Whether extraction succeeded
- `error` – Error message if extraction failed
- `url` – Original URL
- `author` – Article author (if detected)
- `date_published` – Publication date (if detected)
- `language` – Content language (if detected)
- `warnings` – List of extraction warnings

**Options:**

```python
ExtractionOptions(
    min_word_count=150,
    min_char_threshold=500,
    include_images=True,
    include_code_blocks=True,
    safe_markdown=True
)
```

### CLI

```bash
article-extractor https://en.wikipedia.org/wiki/Wikipedia  # Extract from URL
article-extractor --file article.html                      # From file
article-extractor --file article.html --output markdown    # Markdown output
article-extractor --server --port 3000                     # Start server
```

## Use Cases

- **LLM/RAG pipelines** – Extract clean article text for vector databases or prompts
- **Content archiving** – Save web articles as Markdown for documentation
- **RSS/feed readers** – Display clean article content without ads
- **Research tools** – Batch extract articles from reading lists
- **Web scrapers** – Get main content without parsing complex HTML

## How It Works

1. **Parse HTML** – Uses JustHTML's HTML5-compliant parser
2. **Clean document** – Removes scripts, styles, navigation, footers
3. **Find candidates** – Identifies potential content containers (`<article>`, `<main>`, high-scoring divs)
4. **Score candidates** – Applies readability scoring (tag type, class/ID patterns, text density, link density)
5. **Extract winner** – Selects highest-scoring element as main content
6. **Convert to Markdown** – Transforms HTML to clean GFM-compatible Markdown

Algorithm based on [Mozilla Readability.js](https://github.com/mozilla/readability) with Python optimizations.

## Configuration

**Environment variables:**

```bash
HOST=0.0.0.0        # Server bind address
PORT=3000           # Server port
LOG_LEVEL=info      # Logging level (debug, info, warning, error)
WEB_CONCURRENCY=2   # Number of uvicorn workers (auto-tuned in Docker image)
ARTICLE_EXTRACTOR_CACHE_SIZE=1000   # Max in-memory LRU entries (overridable per deployment)
ARTICLE_EXTRACTOR_THREADPOOL_SIZE=0 # Optional override for CPU-bound worker threads (0 = auto)
```

**Production deployment:**

```bash
# With multiple workers
uvicorn article_extractor.server:app \
    --host 0.0.0.0 \
    --port 3000 \
    --workers 4 \
    --log-level info \
    --proxy-headers \
    --forwarded-allow-ips "*" \
    --lifespan=auto

# With Docker (daemon mode)
docker run -d \
    -p 3000:3000 \
    --name article-extractor \
    --restart unless-stopped \
    -e LOG_LEVEL=info \
    -e WEB_CONCURRENCY=4 \
    ghcr.io/pankaj28843/article-extractor:latest
```

## FAQ

**JavaScript-heavy sites?** Install `playwright` extra: `pip install article-extractor[playwright]`

**Extraction fails?** Check `result.success` / `result.error`. Common causes: login required, content too short, JavaScript rendering needed

**Production-ready?** Yes. Pin version: `ghcr.io/pankaj28843/article-extractor:0`

**Rate limiting?** Use reverse proxy (nginx, Caddy) or API gateway

## Development

```bash
git clone https://github.com/pankaj28843/article-extractor.git
cd article-extractor
uv sync --all-extras
uv run pytest
uv run ruff format . && uv run ruff check --fix .
```

**Run server:** `uv run uvicorn article_extractor.server:app --reload --port 3000`

**Structure:**

```
src/article_extractor/
├── server.py    # FastAPI HTTP server
├── cli.py       # CLI interface  
├── extractor.py # Extraction logic
├── scorer.py    # Readability scoring
└── fetcher.py   # URL fetching
```

## Troubleshooting

**Port in use:** `lsof -i :3000` → `uvicorn article_extractor.server:app --port 8000`

**Empty extraction:** Check `result.success`, may need `playwright`, lower `min_word_count`

**Playwright errors:** `playwright install chromium`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, coding standards, and how to run the complete validation loop (`uv run ruff format . && uv run ruff check --fix . && uv run pytest`). Issues and pull requests that include tests and documentation updates are very welcome.

## License

MIT – see [LICENSE](LICENSE)

## Acknowledgments

- [JustHTML](https://github.com/EmilStenstrom/justhtml) – HTML5 parser
- [Mozilla Readability.js](https://github.com/mozilla/readability) – Extraction algorithm
- [readability-js-server](https://github.com/phpdocker-io/readability-js-server) – API design inspiration

---

**Built with ❤️ using pure Python. No Node.js required.**
