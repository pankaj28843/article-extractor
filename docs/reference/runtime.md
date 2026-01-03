# Runtime Interfaces

**Audience & Prereqs**: Developers in the Reference lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table) who need exact commands and API signatures; assume you have already completed the relevant tutorial/how-to.  
**Usage**: Use this page as a lookup; tutorials/how-tos explain workflows and troubleshooting.

Canonical commands and APIs for the CLI, FastAPI server, and Python library.

## CLI Commands

```bash
# Extract from URL (Markdown output)
article-extractor https://en.wikipedia.org/wiki/Wikipedia --output markdown

# Extract from a local file
article-extractor --file article.html --output markdown

# Run with Playwright, proxies, and diagnostics
docker run --rm ghcr.io/pankaj28843/article-extractor:latest \
    article-extractor https://example.com --prefer-playwright \
    --proxy=http://user:pass@proxy:8080 --headed --user-interaction-timeout 30
```

Key options:

- `--output` (`json`, `markdown`, `text`)
- `--min-words` (default 150)
- `--no-images`, `--no-code`
- `--user-agent`, `--random-user-agent`, `--no-random-user-agent`
- `--proxy`, `--prefer-playwright`, `--prefer-httpx`
- `--headed`, `--headless`, `--user-interaction-timeout`
- `--storage-state`
- `--log-level`, `--log-format`

Use `article-extractor --help` (validated in CI) to see the full list.

## FastAPI Server

```bash
uvicorn article_extractor.server:app --host 0.0.0.0 --port 3000
```

Endpoints:

- `POST /` — Extract article (`{"url": "..."}` plus optional `prefer_playwright` + `network` overrides).
- `GET /` — Service info.
- `GET /health` — Health check.
- `GET /docs` — Interactive OpenAPI UI.

See [Networking Controls](../how-to/networking.md#3-fastapi-overrides) for the JSON schema of the `network` block.

## Python API

```python
from article_extractor import (
    extract_article,
    extract_article_from_url,
    ExtractionOptions,
)

options = ExtractionOptions(min_word_count=120, include_images=True)
result = extract_article("<html>...</html>", url="https://example.com", options=options)

print(result.title)
print(result.excerpt)
print(result.success)
```

`ArticleResult` fields:

- `title`, `content`, `markdown`, `excerpt`
- `word_count`, `success`, `error`
- `url`, `author`, `date_published`, `language`
- `warnings` (list of strings describing fallbacks or missing metadata)

Use `extract_article_from_url_async` inside async contexts to fetch via httpx/Playwright without blocking.

## Use Cases

- **LLM & RAG ingestion**: feed the Markdown output into embedding pipelines without extra sanitization.
- **Content archiving**: store cleaned Markdown or HTML snapshots for compliance.
- **RSS/readers**: transform noisy feeds into readable summaries.
- **Research pipelines**: batch-extract large reading lists by calling the CLI or server in parallel.

Additional design rationale lives under [Why Teams Choose Article Extractor](../explanations/why.md) and [How It Works](../explanations/how-it-works.md).
