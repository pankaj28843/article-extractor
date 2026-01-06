#!/usr/bin/env python3
"""Command-line interface for article extraction.

Usage:
    article-extractor <url>                    # Extract from URL
    article-extractor --file <path>            # Extract from HTML file
    echo '<html>...</html>' | article-extractor  # Extract from stdin
    article-extractor crawl --seed URL --output-dir PATH  # Crawl multiple pages
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from .extractor import extract_article, extract_article_from_url
from .network import resolve_network_options
from .observability import build_metrics_emitter, setup_logging, strip_url
from .settings import get_settings
from .types import CrawlConfig, ExtractionOptions, NetworkOptions

logger = logging.getLogger(__name__)


def _describe_source(args: argparse.Namespace) -> str | None:
    if getattr(args, "url", None):
        return strip_url(args.url)
    if getattr(args, "file", None):
        return f"file://{args.file}"
    if getattr(args, "stdin", False):
        return "stdin"
    return None


def _metrics_source_label(args: argparse.Namespace) -> str:
    if getattr(args, "url", None):
        return "url"
    if getattr(args, "file", None):
        return "file"
    if getattr(args, "stdin", False):
        return "stdin"
    return "unknown"


def _record_cli_metrics(
    metrics,
    *,
    success: bool,
    duration_ms: float,
    source: str,
    output: str | None,
) -> None:
    if metrics is None or not getattr(metrics, "enabled", False):
        return
    tags = {"source": source, "output": (output or "json")}
    metric_name = "cli_extractions_total" if success else "cli_extractions_failed_total"
    metrics.increment(metric_name, tags=tags)
    metrics.observe(
        "cli_extraction_duration_ms",
        value=duration_ms,
        tags={**tags, "success": "true" if success else "false"},
    )


def _prompt_output_dir() -> Path:
    """Prompt user for output directory path interactively."""
    if not sys.stdin.isatty():
        print(
            "Error: --output-dir is required in non-interactive mode",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Input required: Enter output directory path: ", end="", flush=True)
    user_input = input().strip()
    if not user_input:
        print("Error: Output directory cannot be empty", file=sys.stderr)
        sys.exit(1)

    return Path(user_input).expanduser().resolve()


def _print_crawl_progress(progress) -> None:
    """Print crawl progress to stderr."""
    from .crawler import CrawlProgress

    if not isinstance(progress, CrawlProgress):
        return

    status_symbol = {
        "fetching": "⏳",
        "success": "✓",
        "failed": "✗",
        "skipped": "⊘",
    }.get(progress.status, "?")

    # Truncate URL for display
    url_display = progress.url
    if len(url_display) > 60:
        url_display = url_display[:57] + "..."

    print(
        f"{status_symbol} [{progress.successful}/{progress.fetched}] {url_display}",
        file=sys.stderr,
    )


async def _run_crawl_command(
    args: argparse.Namespace,
    network: NetworkOptions,
) -> int:
    """Execute the crawl subcommand."""
    from .crawler import CrawlProgress, run_crawl, validate_output_dir

    # Get output directory (prompt if not provided)
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
    else:
        output_dir = _prompt_output_dir()

    # Validate output directory early
    try:
        validate_output_dir(output_dir, create=True)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    worker_count = args.workers if getattr(args, "workers", None) is not None else 1
    if worker_count < 1:
        print("Error: --workers must be at least 1", file=sys.stderr)
        return 1

    config = CrawlConfig(
        output_dir=output_dir,
        seeds=list(args.seed) if args.seed else [],
        sitemaps=list(args.sitemap) if args.sitemap else [],
        allow_prefixes=list(args.allow_prefix) if args.allow_prefix else [],
        deny_prefixes=list(args.deny_prefix) if args.deny_prefix else [],
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        concurrency=args.concurrency,
        worker_count=worker_count,
        rate_limit_delay=args.rate_limit,
        follow_links=args.follow_links,
    )

    # Validate we have at least one seed or sitemap
    if not config.seeds and not config.sitemaps:
        print(
            "Error: At least one --seed or --sitemap is required",
            file=sys.stderr,
        )
        return 1

    print(f"Starting crawl to {output_dir}", file=sys.stderr)
    print(
        f"Seeds: {len(config.seeds)}, Sitemaps: {len(config.sitemaps)}, "
        f"Max pages: {config.max_pages}",
        file=sys.stderr,
    )
    print(
        f"Concurrency: {config.concurrency}, Workers: {config.worker_count}",
        file=sys.stderr,
    )
    print("-" * 60, file=sys.stderr)

    start_time = time.perf_counter()

    # Progress callback
    def on_progress(progress: CrawlProgress) -> None:
        _print_crawl_progress(progress)

    try:
        manifest = await run_crawl(
            config,
            network=network,
            on_progress=on_progress,
        )
    except KeyboardInterrupt:
        print("\nCrawl interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        logger.exception("Crawl failed")
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    duration = time.perf_counter() - start_time

    # Print summary
    print("-" * 60, file=sys.stderr)
    print(f"Crawl complete in {duration:.1f}s", file=sys.stderr)
    print(
        f"  Total: {manifest.total_pages}, "
        f"Successful: {manifest.successful}, "
        f"Failed: {manifest.failed}, "
        f"Skipped: {manifest.skipped}",
        file=sys.stderr,
    )
    print(f"  Output: {output_dir}", file=sys.stderr)
    print(f"  Manifest: {output_dir / 'manifest.json'}", file=sys.stderr)

    return 0 if manifest.failed == 0 else 1


def _add_network_args(parser: argparse.ArgumentParser) -> None:
    """Add common network-related arguments to a parser."""
    parser.add_argument(
        "--user-agent",
        help="Explicit User-Agent header to send with outbound requests",
    )
    ua_group = parser.add_mutually_exclusive_group()
    ua_group.add_argument(
        "--random-user-agent",
        dest="random_user_agent",
        action="store_const",
        const=True,
        help="Randomize User-Agent using fake-useragent when possible",
    )
    ua_group.add_argument(
        "--no-random-user-agent",
        dest="random_user_agent",
        action="store_const",
        const=False,
        help="Disable User-Agent randomization (default)",
    )
    parser.set_defaults(random_user_agent=None)

    parser.add_argument(
        "--proxy",
        help="Proxy URL for outbound requests (overrides HTTP(S)_PROXY env)",
    )

    headed_group = parser.add_mutually_exclusive_group()
    headed_group.add_argument(
        "--headed",
        dest="headed",
        action="store_const",
        const=True,
        help="Launch Playwright in headed mode for manual challenge solving",
    )
    headed_group.add_argument(
        "--headless",
        dest="headed",
        action="store_const",
        const=False,
        help="Force headless Playwright mode (default)",
    )
    parser.set_defaults(headed=None)

    parser.add_argument(
        "--user-interaction-timeout",
        type=float,
        default=None,
        help="Seconds to wait for manual interaction when headed (default: 0)",
    )

    parser.add_argument(
        "--storage-state",
        type=Path,
        default=None,
        help="Path to persist Playwright storage_state.json between runs (default: disabled)",
    )


def _add_logging_args(parser: argparse.ArgumentParser) -> None:
    """Add common logging-related arguments to a parser."""
    parser.add_argument(
        "--log-level",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Override log level",
    )
    parser.add_argument(
        "--log-format",
        choices=["json", "text"],
        help="Select log formatter (default: json)",
    )


def main() -> int:
    """Main CLI entry point."""
    # Check if first arg is 'crawl' subcommand
    if len(sys.argv) > 1 and sys.argv[1] == "crawl":
        return _crawl_main()

    return _extract_main()


def _crawl_main() -> int:
    """Handle the crawl subcommand."""
    parser = argparse.ArgumentParser(
        prog="article-extractor crawl",
        description="Crawl multiple pages and extract articles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required: seeds or sitemaps
    parser.add_argument(
        "--seed",
        action="append",
        metavar="URL",
        help="Seed URL to start crawling from (can be specified multiple times)",
    )
    parser.add_argument(
        "--sitemap",
        action="append",
        metavar="URL",
        help="Sitemap URL or local file path (can be specified multiple times)",
    )

    # Output directory
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help="Output directory for extracted Markdown files (prompts if not provided)",
    )

    # Filtering
    parser.add_argument(
        "--allow-prefix",
        action="append",
        metavar="PREFIX",
        help="Only crawl URLs starting with this prefix (can be specified multiple times)",
    )
    parser.add_argument(
        "--deny-prefix",
        action="append",
        metavar="PREFIX",
        help="Skip URLs starting with this prefix (can be specified multiple times)",
    )

    # Limits
    parser.add_argument(
        "--max-pages",
        type=int,
        default=100,
        help="Maximum number of pages to crawl (default: 100)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum BFS depth from seed URLs (default: 3)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Maximum concurrent requests (default: 5)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=1.0,
        help="Seconds between requests to same host (default: 1.0)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of concurrent crawl workers (default: 1)",
    )

    # Link following
    follow_group = parser.add_mutually_exclusive_group()
    follow_group.add_argument(
        "--follow-links",
        dest="follow_links",
        action="store_true",
        default=True,
        help="Discover and follow links in crawled pages (default)",
    )
    follow_group.add_argument(
        "--no-follow-links",
        dest="follow_links",
        action="store_false",
        help="Only crawl seed URLs and sitemap URLs",
    )

    # Network options
    _add_network_args(parser)

    # Fetcher preference
    prefer_group = parser.add_mutually_exclusive_group()
    prefer_group.add_argument(
        "--prefer-playwright",
        dest="prefer_playwright",
        action="store_const",
        const=True,
        help="Prefer Playwright fetcher (default)",
    )
    prefer_group.add_argument(
        "--prefer-httpx",
        dest="prefer_playwright",
        action="store_const",
        const=False,
        help="Prefer the faster httpx fetcher",
    )
    parser.set_defaults(prefer_playwright=True)

    # Logging
    _add_logging_args(parser)

    args = parser.parse_args(sys.argv[2:])  # Skip 'article-extractor' and 'crawl'

    settings = get_settings()
    setup_logging(
        component="cli-crawl",
        level=(args.log_level.upper() if args.log_level else "INFO"),
        default_level="INFO",
        log_format=args.log_format or settings.log_format,
    )

    network_env = settings.build_network_env()
    network = resolve_network_options(
        url=None,
        env=network_env,
        user_agent=args.user_agent,
        randomize_user_agent=args.random_user_agent,
        proxy=args.proxy,
        headed=args.headed,
        user_interaction_timeout=args.user_interaction_timeout,
        storage_state_path=args.storage_state,
    )

    return asyncio.run(_run_crawl_command(args, network))


def _extract_main() -> int:  # noqa: PLR0912, PLR0915 - CLI parser intentionally verbose
    """Handle the default extract command."""
    parser = argparse.ArgumentParser(
        description="Extract article content from HTML or URLs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Input source
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("url", nargs="?", help="URL to extract article from")
    input_group.add_argument(
        "-f", "--file", type=Path, help="HTML file to extract from"
    )
    input_group.add_argument(
        "--stdin", action="store_true", help="Read HTML from stdin"
    )

    # Output format
    parser.add_argument(
        "-o",
        "--output",
        choices=["json", "markdown", "text"],
        default="json",
        help="Output format (default: json)",
    )

    # Extraction options
    parser.add_argument(
        "--min-words", type=int, default=150, help="Minimum word count (default: 150)"
    )
    parser.add_argument(
        "--no-images", action="store_true", help="Exclude images from output"
    )
    parser.add_argument(
        "--no-code", action="store_true", help="Exclude code blocks from output"
    )

    # Networking options
    parser.add_argument(
        "--user-agent",
        help="Explicit User-Agent header to send with outbound requests",
    )
    ua_group = parser.add_mutually_exclusive_group()
    ua_group.add_argument(
        "--random-user-agent",
        dest="random_user_agent",
        action="store_const",
        const=True,
        help="Randomize User-Agent using fake-useragent when possible",
    )
    ua_group.add_argument(
        "--no-random-user-agent",
        dest="random_user_agent",
        action="store_const",
        const=False,
        help="Disable User-Agent randomization (default)",
    )
    parser.set_defaults(random_user_agent=None)

    parser.add_argument(
        "--proxy",
        help="Proxy URL for outbound requests (overrides HTTP(S)_PROXY env)",
    )

    headed_group = parser.add_mutually_exclusive_group()
    headed_group.add_argument(
        "--headed",
        dest="headed",
        action="store_const",
        const=True,
        help="Launch Playwright in headed mode for manual challenge solving",
    )
    headed_group.add_argument(
        "--headless",
        dest="headed",
        action="store_const",
        const=False,
        help="Force headless Playwright mode (default)",
    )
    parser.set_defaults(headed=None)

    parser.add_argument(
        "--user-interaction-timeout",
        type=float,
        default=None,
        help="Seconds to wait for manual interaction when headed (default: 0)",
    )

    parser.add_argument(
        "--storage-state",
        type=Path,
        default=None,
        help="Path to persist Playwright storage_state.json between runs (default: disabled)",
    )

    # Server mode
    parser.add_argument(
        "--server",
        action="store_true",
        help="Start HTTP server instead of extracting",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Server host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=3000, help="Server port (default: 3000)"
    )

    prefer_group = parser.add_mutually_exclusive_group()
    prefer_group.add_argument(
        "--prefer-playwright",
        dest="prefer_playwright",
        action="store_const",
        const=True,
        help="Prefer Playwright fetcher when both options are available (default)",
    )
    prefer_group.add_argument(
        "--prefer-httpx",
        dest="prefer_playwright",
        action="store_const",
        const=False,
        help="Prefer the faster httpx fetcher when possible",
    )
    parser.set_defaults(prefer_playwright=True)

    parser.add_argument(
        "--log-level",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Override CLI log level (default: critical)",
    )
    parser.add_argument(
        "--log-format",
        choices=["json", "text"],
        help="Select log formatter (default: json)",
    )

    args = parser.parse_args()
    source_label = _metrics_source_label(args)

    settings = get_settings()
    setup_logging(
        component="cli",
        level=(args.log_level.upper() if args.log_level else settings.log_level),
        default_level="CRITICAL",
        log_format=args.log_format or settings.log_format,
    )
    metrics = build_metrics_emitter(
        component="cli",
        enabled=settings.metrics_enabled,
        sink=settings.metrics_sink,
        statsd_host=settings.metrics_statsd_host,
        statsd_port=settings.metrics_statsd_port,
        namespace=settings.metrics_namespace,
    )
    diagnostics_enabled = settings.log_diagnostics
    prefer_playwright = (
        args.prefer_playwright
        if args.prefer_playwright is not None
        else settings.prefer_playwright
    )
    network_env = settings.build_network_env()

    network = resolve_network_options(
        url=args.url,
        env=network_env,
        user_agent=args.user_agent,
        randomize_user_agent=args.random_user_agent,
        proxy=args.proxy,
        headed=args.headed,
        user_interaction_timeout=args.user_interaction_timeout,
        storage_state_path=args.storage_state,
    )

    source_hint = _describe_source(args)

    # Server mode
    if args.server:
        try:
            import uvicorn

            from .server import app, configure_network_defaults, set_prefer_playwright

            configure_network_defaults(network)
            set_prefer_playwright(prefer_playwright)
            logger.info(
                "Starting FastAPI server",
                extra={"host": args.host, "port": args.port},
            )
            if getattr(metrics, "enabled", False):
                metrics.increment(
                    "cli_server_start_total",
                    tags={"host": args.host, "port": str(args.port)},
                )
            uvicorn.run(app, host=args.host, port=args.port)
            return 0
        except ImportError as exc:
            logger.error(
                "Server dependencies not installed",
                extra={"host": args.host, "port": args.port},
                exc_info=exc,
            )
            print("Error: Server dependencies not installed", file=sys.stderr)
            print(
                "Install with: pip install article-extractor[server]", file=sys.stderr
            )
            return 1

    # Extract mode
    options = ExtractionOptions(
        min_word_count=args.min_words,
        include_images=not args.no_images,
        include_code_blocks=not args.no_code,
    )

    duration_start: float | None = None

    try:
        if source_hint:
            logger.info("Extracting article", extra={"url": source_hint})
        # Determine input source
        duration_start = time.perf_counter()
        if args.url:
            result = asyncio.run(
                extract_article_from_url(
                    args.url,
                    options=options,
                    network=network,
                    prefer_playwright=prefer_playwright,
                    diagnostic_logging=diagnostics_enabled,
                )
            )
        elif args.file:
            html = args.file.read_text(encoding="utf-8")
            result = extract_article(html, url=str(args.file), options=options)
        else:
            # Read from stdin
            html = sys.stdin.read()
            result = extract_article(html, options=options)

        if not result.success:
            duration_ms = (time.perf_counter() - duration_start) * 1000
            _record_cli_metrics(
                metrics,
                success=False,
                duration_ms=duration_ms,
                source=source_label,
                output=args.output,
            )
            logger.error(
                "Extraction failed",
                extra={
                    "url": source_hint or strip_url(result.url),
                    "error": result.error or "unknown",
                },
            )
            print(f"Error: {result.error}", file=sys.stderr)
            return 1

        duration_ms = (time.perf_counter() - duration_start) * 1000
        _record_cli_metrics(
            metrics,
            success=True,
            duration_ms=duration_ms,
            source=source_label,
            output=args.output,
        )

        # Output result
        if args.output == "json":
            output = {
                "url": result.url,
                "title": result.title,
                "byline": result.author,
                "dir": "ltr",
                "content": result.content,
                "length": len(result.content),
                "excerpt": result.excerpt,
                "siteName": None,
                "markdown": result.markdown,
                "word_count": result.word_count,
                "success": result.success,
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        elif args.output == "markdown":
            print(result.markdown)
        else:  # text
            print(f"Title: {result.title}")
            print(f"Author: {result.author or 'Unknown'}")
            print(f"Words: {result.word_count}")
            print(f"\n{result.excerpt}")

        return 0

    except KeyboardInterrupt:
        duration_ms = (
            (time.perf_counter() - duration_start) * 1000
            if duration_start is not None
            else 0.0
        )
        _record_cli_metrics(
            metrics,
            success=False,
            duration_ms=duration_ms,
            source=source_label,
            output=args.output,
        )
        if source_hint:
            logger.warning("Extraction interrupted", extra={"url": source_hint})
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        duration_ms = (
            (time.perf_counter() - duration_start) * 1000
            if duration_start is not None
            else 0.0
        )
        _record_cli_metrics(
            metrics,
            success=False,
            duration_ms=duration_ms,
            source=source_label,
            output=args.output,
        )
        if source_hint:
            logger.exception("Extraction failed", extra={"url": source_hint})
        print(f"Error: {e!s}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
