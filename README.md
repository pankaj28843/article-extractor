# Article Extractor

**Extract the content you care about from any web page—no JavaScript runtime, no external services, just Python.**

Article Extractor pulls the main content from HTML documents (articles, blog posts, documentation) and converts it to clean Markdown. If you've ever wanted the "Reader Mode" experience in your Python code, this is it.

## Why Article Extractor?

- **Pure Python** – No Node.js, no Selenium, no external APIs. Install it, import it, use it.
- **Battle-tested algorithms** – Uses scoring techniques from Mozilla's Readability.js to identify what's actually content vs. navigation, ads, and sidebars.
- **Markdown output** – Get clean GitHub-Flavored Markdown, ready for LLMs, documentation, or archiving.
- **Fast** – Caches text calculations and uses early termination. Extracts most articles in milliseconds.
- **Safe by default** – XSS-safe output via [JustHTML](https://github.com/EmilStenstrom/justhtml) sanitization.

## Who Is This For?

- **LLM/AI developers** building RAG pipelines or agents that need clean text from web pages
- **Content archivists** who want to save articles as Markdown
- **Researchers** scraping article text for analysis
- **Anyone** tired of wrangling BeautifulSoup to extract "just the article"

## Installation

```bash
# From PyPI
pip install article-extractor

# With optional fetchers
pip install article-extractor[httpx]       # Lightweight HTTP fetcher
pip install article-extractor[playwright]  # JavaScript rendering support
pip install article-extractor[all]         # All optional dependencies

# With uv
uv add article-extractor
uv add article-extractor --extra all       # With all optional dependencies
```

## Quick Start

Here's a complete example—paste this into a Python file and run it:

```python
from article_extractor import extract_article

html = """
<html>
<body>
    <nav><a href="/">Home</a></nav>
    <article>
        <h1>My Article</h1>
        <p>This is the main content of the article...</p>
    </article>
    <footer>Copyright 2025</footer>
</body>
</html>
"""

result = extract_article(html, url="https://example.com/article")

print(result.title)      # "My Article"
print(result.markdown)   # "# My Article\n\nThis is the main content..."
print(result.word_count) # 8
print(result.success)    # True
```

That's it. The library automatically ignores the `<nav>` and `<footer>`, extracts the `<article>`, and gives you clean Markdown.

### Fetching from URLs

Need to fetch a page first? Use the async `extract_article_from_url`:

```python
import asyncio
from article_extractor import extract_article_from_url

async def main():
    result = await extract_article_from_url("https://example.com/some-article")
    print(result.markdown)

asyncio.run(main())
```

By default, this uses Playwright if available (for JavaScript-heavy sites), falling back to httpx.

## How It Works

The extraction algorithm is inspired by Mozilla's Readability.js (the engine behind Firefox Reader View):

1. **Parse HTML** – Uses JustHTML's HTML5-compliant parser
2. **Clean the document** – Removes scripts, styles, nav, footer, and other non-content elements
3. **Find candidates** – Looks for `<article>`, `<main>`, or high-scoring `<div>`/`<section>` elements
4. **Score candidates** – Each element gets a score based on:
   - Tag type (`article`: +5, `div`: +5, `h1-h6`: -5)
   - Class/ID patterns (+25 for "article", "content"; -25 for "sidebar", "footer")
   - Paragraph content (+1 per comma, +1 per 100 characters)
   - Link density (high link ratio = probably navigation, penalized)
5. **Extract the winner** – Takes content from the highest-scoring candidate
6. **Convert to Markdown** – Uses JustHTML's GFM-compatible converter

## API Reference

### `extract_article(html, url="", options=None) -> ArticleResult`

Extract article content from an HTML string.

| Parameter | Type | Description |
|-----------|------|-------------|
| `html` | `str \| bytes` | HTML content to extract from |
| `url` | `str` | Original URL (used for resolving relative links and title fallback) |
| `options` | `ExtractionOptions \| None` | Extraction configuration (see below) |

**Returns:** `ArticleResult` with extracted content.

### `extract_article_from_url(url, fetcher=None, options=None, *, prefer_playwright=True) -> ArticleResult`

Async function to fetch a URL and extract article content.

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | URL to fetch |
| `fetcher` | `Fetcher \| None` | Custom fetcher (auto-creates if not provided) |
| `options` | `ExtractionOptions \| None` | Extraction configuration |
| `prefer_playwright` | `bool` | Prefer Playwright over httpx when auto-creating (default: `True`) |

### `ArticleResult`

The result object returned by extraction functions:

```python
@dataclass
class ArticleResult:
    url: str                       # Original URL
    title: str                     # Extracted title
    content: str                   # Cleaned HTML content
    markdown: str                  # Markdown conversion
    excerpt: str                   # Short excerpt (~200 chars)
    word_count: int                # Word count of extracted content
    success: bool                  # Whether extraction succeeded
    error: str | None = None       # Error message if failed
    author: str | None = None      # Author (if found)
    date_published: str | None = None  # Publication date (if found)
    language: str | None = None    # Document language (if detected)
    warnings: list[str] = []       # Non-fatal warnings
```

### `ExtractionOptions`

Configure extraction behavior:

```python
@dataclass
class ExtractionOptions:
    min_word_count: int = 150       # Minimum words for valid content
    min_char_threshold: int = 500   # Minimum chars for candidate consideration
    include_images: bool = True     # Include images in output
    include_code_blocks: bool = True # Include code blocks
    safe_markdown: bool = True      # XSS-safe output (recommended)
```

## FAQ

**Q: Why not just use BeautifulSoup?**  
BeautifulSoup parses HTML, but doesn't know what's "content" vs. "navigation." You'd need to write heuristics yourself. Article Extractor has those heuristics built in.

**Q: Does this work on JavaScript-heavy sites?**  
If you install the `playwright` extra, yes. The async fetcher will render the page with a real browser before extraction.

**Q: What if extraction fails?**  
Check `result.success` and `result.error`. Common issues: page is behind a login, content is too short (below `min_word_count`), or the site uses an unusual structure.

**Q: Can I customize what gets extracted?**  
Use `ExtractionOptions` to tune thresholds. For more control, you can also pre-process the HTML before passing it to `extract_article`.

## Development

Contributions are welcome! Here's how to get set up:

```bash
# Clone and install
git clone https://github.com/pankaj28843/article-extractor.git
cd article-extractor
uv sync --all-extras

# Run tests
uv run pytest

# Format and lint
uv run ruff format .
uv run ruff check --fix .

# Run with coverage
uv run pytest --cov
```

### Project Structure

```
src/article_extractor/
├── __init__.py      # Public API (extract_article, extract_article_from_url)
├── extractor.py     # Main extraction logic
├── scorer.py        # Readability-style scoring algorithm
├── fetcher.py       # URL fetching (httpx, Playwright)
├── cache.py         # Text calculation caching
├── constants.py     # Scoring weights, tag lists
├── types.py         # Data classes (ArticleResult, ExtractionOptions)
└── utils.py         # Helper functions
```

## License

MIT License – see [LICENSE](LICENSE) for details.

## Acknowledgments

- [JustHTML](https://github.com/EmilStenstrom/justhtml) – Pure Python HTML5 parser and Markdown converter
- [Mozilla Readability.js](https://github.com/mozilla/readability) – Scoring algorithm inspiration
- [Postlight Parser](https://github.com/postlight/parser) – Additional scoring patterns
