# Crawling

Batch-extract articles from multiple pages using the integrated crawler. The crawler supports BFS traversal from seed URLs, sitemap ingestion, URL filtering, and automatic Markdown output with manifest tracking.

**Audience**: Developers running multi-page extraction workflows.  
**Prerequisites**: CLI installed and write access to the output directory.  
**Time**: ~10-20 minutes for the first crawl run.  
**What you'll learn**: How to seed, configure, and verify crawler output.

## Quick Start

### CLI

```bash
# Crawl from a seed URL
uv run article-extractor crawl \
  --seed https://example.com/blog \
  --output-dir ./crawl-output

# Crawl from a sitemap
uv run article-extractor crawl \
  --sitemap https://example.com/sitemap.xml \
  --output-dir ./crawl-output

# Combine seeds and sitemaps with filters
uv run article-extractor crawl \
  --seed https://example.com/docs \
  --sitemap https://example.com/sitemap.xml \
  --allow-prefix https://example.com/docs/ \
  --deny-prefix https://example.com/docs/private/ \
  --max-pages 50 \
  --output-dir ./docs-crawl
```

### HTTP API

```bash
# Submit a crawl job
curl -X POST http://localhost:3000/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "output_dir": "/data/crawl-output",
    "seeds": ["https://example.com/blog"],
    "max_pages": 100
  }'

# Response: {"job_id": "abc-123", "status": "queued", ...}

# Poll job status
curl http://localhost:3000/crawl/abc-123

# Download manifest when complete
curl http://localhost:3000/crawl/abc-123/manifest -o manifest.json
```

## Configuration

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--seed URL` | — | Seed URL to start crawling (repeatable) |
| `--sitemap URL` | — | Sitemap URL or local file path (repeatable) |
| `--output-dir PATH` | prompts | Output directory for Markdown files |
| `--allow-prefix PREFIX` | all | Only crawl URLs starting with prefix (repeatable) |
| `--deny-prefix PREFIX` | none | Skip URLs starting with prefix (repeatable) |
| `--max-pages N` | 100 | Maximum pages to crawl |
| `--max-depth N` | 3 | Maximum BFS depth from seeds |
| `--concurrency N` | 5 | Concurrent requests |
| `--rate-limit SECONDS` | 1.0 | Delay between requests to same host |
| `--follow-links` | true | Discover and follow links in pages |
| `--no-follow-links` | — | Only crawl seed/sitemap URLs |

Network options (`--headed`, `--storage-state`, `--prefer-playwright`, etc.) work identically to single-URL extraction.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARTICLE_EXTRACTOR_CRAWLER_CONCURRENCY` | 5 | Default concurrent requests |
| `ARTICLE_EXTRACTOR_CRAWLER_RATE_LIMIT` | 1.0 | Default rate limit delay |
| `ARTICLE_EXTRACTOR_CRAWLER_MAX_PAGES` | 100 | Default page limit |

## Output Structure

All extracted pages are saved as flat Markdown files in the output directory. Path separators (`/`) in URLs are replaced with double underscores (`__`) to create a flat structure:

```
output-dir/
├── manifest.json                           # Crawl metadata and results
├── example.com__blog.md
├── example.com__blog__post-1.md
├── example.com__blog__post-2.md
└── docs.example.com__getting-started.md
```

For deeply nested URLs (like wiki pages), the flat structure avoids excessive directory nesting:

```
# URL: https://wiki.example.com/spaces/DOCS/pages/12345678/GettingStarted
# File: wiki.example.com__spaces__DOCS__pages__12345678__GettingStarted.md
```

### Markdown Format

Each extracted page is saved as a Markdown file with YAML frontmatter:

```markdown
---
url: "https://example.com/blog/post-1"
title: "My First Blog Post"
extracted_at: "2026-01-05T12:30:00Z"
word_count: 1500
---

# My First Blog Post

Article content in Markdown format...
```

### Manifest Schema

```json
{
  "job_id": "abc-123",
  "started_at": "2026-01-05T12:00:00Z",
  "completed_at": "2026-01-05T12:30:00Z",
  "config": {
    "seeds": ["https://example.com/blog"],
    "max_pages": 100,
    "concurrency": 5
  },
  "total_pages": 42,
  "successful": 40,
  "failed": 1,
  "skipped": 1,
  "duration_seconds": 1800.5,
  "results": [
    {
      "url": "https://example.com/blog/post-1",
      "file_path": "example.com__blog__post-1.md",
      "status": "success",
      "word_count": 1500,
      "title": "My First Blog Post"
    }
  ]
}
```

## URL Filtering

The crawler applies filters in order:

1. **Allow prefixes** — If specified, URL must start with at least one prefix
2. **Deny prefixes** — URL is rejected if it starts with any deny prefix
3. **Same-origin** — By default, only URLs from the same origin as seeds are followed

```bash
# Crawl only /docs/ pages, excluding /docs/internal/
uv run article-extractor crawl \
  --seed https://example.com/docs \
  --allow-prefix https://example.com/docs/ \
  --deny-prefix https://example.com/docs/internal/ \
  --output-dir ./docs
```

## Rate Limiting

The crawler enforces per-host rate limiting to avoid overloading servers:

- Default: 1 second between requests to the same host
- Concurrent requests are limited to different hosts
- 429 responses trigger exponential backoff

```bash
# Slower crawl for sensitive servers
uv run article-extractor crawl \
  --seed https://fragile-server.com \
  --rate-limit 3.0 \
  --concurrency 2 \
  --output-dir ./output
```

## Headed Mode for Protected Sites

For sites requiring authentication or CAPTCHA solving:

```bash
# Interactive crawl with stored session
uv run article-extractor crawl \
  --seed https://protected-site.com \
  --headed \
  --storage-state ./session.json \
  --user-interaction-timeout 60 \
  --max-pages 20 \
  --output-dir ./protected-output
```

The crawler pauses on the first page to let you log in, then continues automatically.

## API Endpoints

### POST /crawl

Submit a new crawl job.

**Request:**
```json
{
  "output_dir": "/data/output",
  "seeds": ["https://example.com"],
  "sitemaps": [],
  "allow_prefixes": [],
  "deny_prefixes": [],
  "max_pages": 100,
  "max_depth": 3,
  "concurrency": 5,
  "rate_limit_delay": 1.0,
  "follow_links": true,
  "network": {
    "headed": false,
    "storage_state": null
  }
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "abc-123",
  "status": "queued",
  "progress": 0,
  "total": 0
}
```

### GET /crawl/{job_id}

Poll job status.

**Response:**
```json
{
  "job_id": "abc-123",
  "status": "running",
  "progress": 25,
  "total": 100,
  "successful": 24,
  "failed": 1,
  "skipped": 0,
  "started_at": "2026-01-05T12:00:00Z"
}
```

Status values: `queued`, `running`, `completed`, `failed`

### GET /crawl/{job_id}/manifest

Download the manifest.json for a completed job.

**Response:** The manifest JSON file.

**Errors:**
- 404 if job not found
- 400 if job not completed

## Troubleshooting

### Crawl hangs or times out

- Reduce `--concurrency` to avoid overwhelming servers
- Increase `--rate-limit` for rate-limited sites
- Use `--headed` mode to debug JavaScript-heavy pages

### Missing pages

- Check `manifest.json` for failed/skipped entries
- Verify URL filters aren't too restrictive
- Ensure `--max-depth` is sufficient for deep hierarchies

### Disk space warnings

The crawler warns if output directory has less than 100MB free. For large crawls:

```bash
# Check available space before crawling
df -h /path/to/output

# Use --max-pages to limit scope
uv run article-extractor crawl \
  --seed https://large-site.com \
  --max-pages 500 \
  --output-dir /data/large-crawl
```
