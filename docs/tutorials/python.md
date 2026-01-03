# Python Tutorial: Embed the Extractor in Your Codebase

**Audience & Prereqs**: Python developers in the Tutorials lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table); bring Python 3.12+, package-install access, and outbound HTTPS for live fetches.  
**Time**: ~5 minutes including installation and async fetch verification.  
**What you'll learn**: Installing the library, extracting from raw HTML, fetching live URLs asynchronously, and interpreting the results.

## 1. Install the Library

```bash
uv pip install article-extractor --upgrade
```

Use `[server]` or `[all]` extras when you deploy the FastAPI service or Playwright fetchers alongside your Python code.

## 2. Extract Inline HTML

Run the snippet directly via `uv run python` so it uses the locked environment:

```bash
uv run python - <<'PY'
from article_extractor import extract_article

sample_html = """
<html><body><article><h1>Sample Title</h1><p>Some content for docs.</p></article></body></html>
"""

result = extract_article(sample_html, url="https://example.com/demo")
print("Local title:", result.title)
print("Local words:", result.word_count)
PY
```

Sample output:

```text
Local title: Sample Title
Local words: 6
```

Pass the `url` argument even for inline HTML so scoring heuristics can derive language/domain hints.

## 3. Fetch a Live URL (Async)

`extract_article_from_url` returns a coroutine. Wrap it with `asyncio.run` (or your framework's event loop) and execute with `uv run python`:

```bash
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

Sample output (2026-01-03):

```text
Remote success: True
Remote words: 33414
```

## Verification Checklist

- `extract_article` returns an `ArticleResult` with the provided title and non-zero word count.
- The async example exits 0 and prints `Remote success: True` plus a positive word count.
- Network calls respect your proxy/env settings; see [How-To: Networking Controls](../how-to/networking.md#2-cli-flags-for-networking) if you need overrides.

## Troubleshooting

- **Event loop already running**: Use `asyncio.get_event_loop`/`create_task` within your framework instead of `asyncio.run`.
- **Missing Playwright/httpx extras**: Install `[all]` or the specific extra you need (`pip install article-extractor[playwright]`).
- **Proxy/Auth failures**: Configure `HTTP(S)_PROXY` env vars or pass a `NetworkOptions` instance as shown in [Runtime Reference](../reference/runtime.md#python-api).

## Next Steps

1. Review every `ExtractionOptions` field in the [Runtime Reference](../reference/runtime.md#python-api) to control Markdown images, word limits, or candidate filtering.
2. Pipe results into embeddings pipelines or storage layers as described in [Use Cases](../explanations/why.md#use-cases).
3. Graduate to batch/async pipelines by pairing this tutorial with [How-To: Diagnostics & Metrics](../how-to/diagnostics.md).
