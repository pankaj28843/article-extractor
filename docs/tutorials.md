# Tutorials

Each tutorial embeds the exact commands and trimmed output captured on 2026-01-03. Swap URLs as needed, but keep the verification steps so you know when to trust the scorer.

**Audience**: Developers running the CLI, Docker service, or Python API for the first time.  
**Prerequisites**: Python 3.12+, outbound HTTPS, and `uv` on PATH (Docker optional).  
**Time**: ~10-20 minutes depending on the path you pick.  
**What you'll learn**: How to run the CLI, start the server, and validate results.

## CLI Fast Path

**Arrange**
- Python 3.12+, outbound HTTPS, and `uv` on PATH.
- Writable `./tmp/` directory for scratch files.

**Act**

```bash
uv pip install article-extractor --upgrade
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia --output markdown > ./tmp/article-extractor-cli.md
head -n 12 ./tmp/article-extractor-cli.md
```

Sample output:

```text
Resolved 9 packages in 425ms
Installed 1 package in 5ms
Title: Wikipedia - Wikipedia
Author: Unknown
Words: 33414
[<img alt="Page extended-confirmed-protected" ...]
```

**Assert**
- Install command exits 0 and reports the new version.
- CLI banner shows title/word count plus non-empty Markdown written to `./tmp/article-extractor-cli.md`.
- Use `--output json` whenever you need structured warnings for pipelines.

## Docker Service

**Arrange**
- Docker 24+, permission to pull from `ghcr.io` and bind a host port.
- Optional host volume for Playwright storage (`$HOME/.article-extractor`).

**Act**

```bash
docker run --rm -d -p 3000:3000 --name article-extractor-docs ghcr.io/pankaj28843/article-extractor:latest
curl -sf http://localhost:3000/health
docker logs --tail 6 article-extractor-docs
curl -s -XPOST http://localhost:3000/ \
  -H "Content-Type: application/json" \
  -d '{"url":"https://en.wikipedia.org/wiki/Wikipedia"}' | jq '.title, .word_count'
docker stop article-extractor-docs
```

Observed output (2026-01-03):

```text
INFO:     Uvicorn running on http://0.0.0.0:3000 (Press CTRL+C to quit)
"Wikipedia - Wikipedia"
33414
```

**Assert**
- Container stays in `running` per `docker ps` and logs the uvicorn banner.
- `/health` responds with HTTP 200 JSON.
- POST returns a title + positive word count before you stop the container.
- Default containers stay ephemeral; add `-v $HOME/.article-extractor:/data` plus `-e ARTICLE_EXTRACTOR_STORAGE_STATE_FILE=/data/storage_state.json` only when you want to persist cookies.

## Python Embedding

**Arrange**
- Same environment as the CLI fast path plus outbound HTTPS for live fetches.

**Act**

```bash
uv pip install article-extractor --upgrade
uv run python - <<'PY'
from article_extractor import extract_article
sample_html = """
<html><body><article><h1>Sample Title</h1><p>Docs content.</p></article></body></html>
"""
result = extract_article(sample_html, url="https://example.com/demo")
print("Local title:", result.title)
print("Local words:", result.word_count)
PY

uv run python - <<'PY'
import asyncio
from article_extractor import extract_article_from_url
async def fetch_remote():
    result = await extract_article_from_url("https://en.wikipedia.org/wiki/Wikipedia")
    print("Remote success:", result.success)
    print("Remote words:", result.word_count)
asyncio.run(fetch_remote())
PY
```

**Assert**
- Inline HTML example prints the provided title and a positive word count.
- Async fetch prints `Remote success: True` and a word count around 33k, matching CLI/Docker runs.
- Pass `NetworkOptions` or `FetchPreferences` arguments whenever you need proxies, user-agents, or headed Playwright (see [Networking Controls](operations.md#networking-controls)).
