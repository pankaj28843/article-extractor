# CLI Tutorial: Extract an Article in 2 Minutes

**Audience & Prereqs**: CLI operators in the Tutorials lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table); bring Python 3.12+, outbound HTTPS, and either `uv pip` or `pip`.  
**Time**: < 2 minutes once Python is installed.  
**What you'll learn**: Installing the package, extracting a public URL, saving Markdown, and confirming success with real output.

## 1. Install the CLI

Use `uv pip` (preferred) or `pip` to install the wheel from PyPI:

```bash
uv pip install article-extractor --upgrade
```

Sample run (2026-01-03):

```text
$ uv pip install article-extractor --upgrade
Resolved 9 packages in 425ms
Prepared 1 package in 132ms
Uninstalled 1 package in 1ms
Installed 1 package in 5ms
 - justhtml==0.27.0
 + justhtml==0.29.0
```

## 2. Extract a Page

Run the CLI against Wikipedia and redirect the Markdown to `./tmp/article-extractor-cli.md` (repo-local temp storage stays permissionless and gitignored) so you can inspect it without fighting terminal scrollback:

```bash
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia --output markdown > ./tmp/article-extractor-cli.md
```

Inspect the first few lines:

```text
$ head -n 12 ./tmp/article-extractor-cli.md
[<img alt="Page extended-confirmed-protected" src="https://upload.wikimedia.org/wikipedia/en/thumb/8/8c/Extended-protection-shackle.svg/20px-Extended-protection-shackle.svg.png" ...]
From Wikipedia, the free encyclopedia

Free online crowdsourced encyclopedia

This article is about the online encyclopedia. For Wikipedia's home page, see [Main Page](/wiki/Main_Page)...
```

The command prints the detected title, excerpt, and word count before streaming Markdown. Use `--output json` if you prefer structured data.

## 3. Capture Markdown for Later

Pipe the output to `tee` or your editor to keep a copy:

```bash
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia --output markdown | tee wikipedia.md
```

Use `less -R wikipedia.md` to skim the content with ANSI colors intact.

## Verification Checklist

- `uv pip install …` exits 0 and reports the installed versions (see sample above).
- `uv run article-extractor …` exits 0, prints the metadata banner, and writes Markdown to `./tmp/article-extractor-cli.md` (or your chosen path).
- The saved Markdown contains headings plus paragraphs, proving the scorer found the main article block.

## Troubleshooting

- **Proxy errors**: Follow [Networking Controls](../how-to/networking.md#1-prep-environment-variables) to export `HTTP(S)_PROXY`/`NO_PROXY` or pass `--proxy=…` once.
- **Short output**: Lower `--min-words` or inspect warnings via `--output json`.
- **Bot/CAPTCHA challenges**: Install the Playwright extra (`pip install article-extractor[all]`) and rerun with `--headed --user-interaction-timeout 30`.

## Next Steps

1. Deploy the FastAPI server in Docker via the [5-minute tutorial](docker.md).
2. Embed `extract_article()` using the [Python walk-through](python.md).
3. Apply production settings (cache, storage, metrics) with [Override Cache & Playwright Storage](../how-to/cache-playwright.md).
