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
import sys
from pathlib import Path

from .extractor import extract_article, extract_article_from_url
from .types import ExtractionOptions


def main() -> int:
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

    args = parser.parse_args()

    # Server mode
    if args.server:
        try:
            import uvicorn

            from .server import app

            uvicorn.run(app, host=args.host, port=args.port)
            return 0
        except ImportError:
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

    try:
        # Determine input source
        if args.url:
            result = asyncio.run(extract_article_from_url(args.url, options=options))
        elif args.file:
            html = args.file.read_text(encoding="utf-8")
            result = extract_article(html, url=str(args.file), options=options)
        else:
            # Read from stdin
            html = sys.stdin.read()
            result = extract_article(html, options=options)

        if not result.success:
            print(f"Error: {result.error}", file=sys.stderr)
            return 1

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
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e!s}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
