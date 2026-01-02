"""Helpers for managing Playwright storage directories.

These utilities centralize all cleanup logic so container scripts
and tests can purge storage paths without duplicating shell code.
"""

from __future__ import annotations

import argparse
import shutil
from collections.abc import Sequence
from pathlib import Path

__all__ = ["purge_storage_directory", "main"]


def purge_storage_directory(path: str | Path) -> Path:
    """Delete all contents under *path* and recreate the directory.

    Args:
        path: Directory to purge. The directory is recreated if it exists.

    Returns:
        A ``Path`` pointing to the recreated directory.
    """

    target = Path(path).expanduser()
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="article-extractor-storage",
        description="Purge and recreate article-extractor storage directories.",
    )
    parser.add_argument(
        "path",
        type=Path,
        help="Directory containing Playwright storage_state.json files.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for ``python -m article_extractor.storage``."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    purge_storage_directory(args.path)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via CLI
    raise SystemExit(main())
