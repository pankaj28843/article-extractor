#!/usr/bin/env python3
"""Command-line interface for article extraction.

Usage:
    article-extractor <url>                    # Extract from URL
    article-extractor --file <path>            # Extract from HTML file
    echo '<html>...</html>' | article-extractor  # Extract from stdin
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
from .types import ExtractionOptions

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


def main() -> int:  # noqa: PLR0912, PLR0915 - CLI parser intentionally verbose
    """Main CLI entry point."""
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
        help="Path for persistent Playwright storage_state.json",
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
