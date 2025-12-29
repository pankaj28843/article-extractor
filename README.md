# Article Extractor

Pure-Python article extraction library that extracts main content from HTML documents and converts to Markdown.

Uses [JustHTML](https://github.com/EmilStenstrom/justhtml) for HTML parsing and implements Readability.js-style scoring for content detection.

## Features

- **Pure Python** - No external services or JavaScript runtime required
- **Readability-style scoring** - Identifies main content using proven algorithms from Mozilla's Readability.js
- **Markdown output** - Converts extracted content to clean GitHub-Flavored Markdown
- **Fast** - Caches text calculations, uses early termination optimizations
- **Safe by default** - XSS-safe HTML and Markdown output via JustHTML sanitization

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

## API Reference

### `extract_article(html, url="", options=None) -> ArticleResult`

Extract main article content from HTML.

**Parameters:**
- `html` (str | bytes): HTML content to extract from
- `url` (str): Original URL (used for title fallback)
- `options` (ExtractionOptions | None): Extraction configuration

**Returns:** `ArticleResult` with extracted content

### `extract_article_from_url(url, fetcher=None, options=None, *, prefer_playwright=True) -> ArticleResult`

Async function to fetch URL and extract article content. If no fetcher is provided, auto-selects the best available fetcher.

**Parameters:**
- `url` (str): URL to fetch
- `fetcher` (Fetcher | None): Object implementing the `Fetcher` protocol (optional - auto-creates if not provided)
- `options` (ExtractionOptions | None): Extraction configuration
- `prefer_playwright` (bool): If auto-creating fetcher, prefer Playwright (default: True)

### `ArticleResult`

```python
@dataclass
class ArticleResult:
    url: str                       # Original URL
    title: str                     # Extracted title
    content: str                   # Cleaned HTML content
    markdown: str                  # Markdown conversion
    excerpt: str                   # Short excerpt (first ~200 chars)
    word_count: int                # Word count of extracted content
    success: bool                  # Whether extraction succeeded
    error: str | None = None       # Error message if failed
    author: str | None = None      # Extracted author (if found)
    date_published: str | None = None  # Publication date (if found)
    language: str | None = None    # Document language (if detected)
    warnings: list[str] = []       # Non-fatal warnings
```

### `ExtractionOptions`

```python
@dataclass
class ExtractionOptions:
    min_word_count: int = 150       # Minimum words for valid content
    min_char_threshold: int = 500   # Minimum chars for candidate consideration
    include_images: bool = True     # Include images in output
    include_code_blocks: bool = True # Include code blocks in output
    safe_markdown: bool = True      # XSS-safe output (recommended)
```

## How It Works

1. **Parse HTML** using JustHTML's HTML5-compliant parser
2. **Clean document** by removing scripts, styles, nav, footer, etc.
3. **Find candidates** - Look for `<article>`, `<main>`, or high-scoring `<div>`/`<section>` elements
4. **Score candidates** using Readability.js-style algorithm:
   - Tag-based scores (article: +5, div: +5, h1-h6: -5)
   - Class/ID pattern matching (+25 for "article", "content"; -25 for "sidebar", "footer")
   - Paragraph content scoring (+1 per comma, +1 per 100 chars)
   - Link density penalty (high link ratio = navigation)
5. **Extract content** from top-scoring candidate
6. **Convert to Markdown** using JustHTML's GFM-compatible converter

## Development

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

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

- [JustHTML](https://github.com/EmilStenstrom/justhtml) - Pure Python HTML5 parser
- [Mozilla Readability.js](https://github.com/mozilla/readability) - Scoring algorithm inspiration
- [Postlight Parser](https://github.com/postlight/parser) - Additional scoring patterns
