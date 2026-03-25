#!/usr/bin/env python3
"""Fail release builds that contain suspicious files or layouts."""

from __future__ import annotations

import argparse
import sys
import tarfile
import zipfile
from pathlib import PurePosixPath

BANNED_SUFFIXES = {
    ".pth",
    ".so",
    ".dylib",
    ".dll",
    ".exe",
    ".bat",
    ".cmd",
    ".ps1",
}
BANNED_FILENAMES = {
    "sitecustomize.py",
    "usercustomize.py",
}
PACKAGE_ROOT = "article_extractor"
DIST_INFO_SUFFIX = ".dist-info"


def _is_suspicious_member(member: str) -> str | None:
    path = PurePosixPath(member)
    name = path.name

    if name in BANNED_FILENAMES:
        return f"banned file name: {member}"

    if path.suffix.lower() in BANNED_SUFFIXES:
        return f"banned file suffix: {member}"

    return None


def _check_wheel(path: str) -> list[str]:
    errors: list[str] = []

    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if member.endswith("/"):
                continue

            suspicious = _is_suspicious_member(member)
            if suspicious:
                errors.append(suspicious)
                continue

            top_level = PurePosixPath(member).parts[0]
            if top_level == PACKAGE_ROOT or top_level.endswith(DIST_INFO_SUFFIX):
                continue

            errors.append(f"unexpected top-level wheel entry: {member}")

    return errors


def _check_sdist(path: str) -> list[str]:
    errors: list[str] = []

    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue

            parts = PurePosixPath(member.name).parts
            rel_path = "/".join(parts[1:]) if len(parts) > 1 else member.name

            suspicious = _is_suspicious_member(rel_path)
            if suspicious:
                errors.append(suspicious)

    return errors


def verify_distribution(path: str) -> list[str]:
    if path.endswith(".whl"):
        return _check_wheel(path)
    if path.endswith(".tar.gz"):
        return _check_sdist(path)
    return [f"unsupported distribution type: {path}"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect built distributions for unexpected executable hooks."
    )
    parser.add_argument("paths", nargs="+", help="Wheel and/or sdist paths to inspect")
    args = parser.parse_args()

    failures = []
    for path in args.paths:
        errors = verify_distribution(path)
        if errors:
            failures.append((path, errors))

    if failures:
        for path, errors in failures:
            sys.stderr.write(f"{path} failed verification:\n")
            for error in errors:
                sys.stderr.write(f"  - {error}\n")
        return 1

    for path in args.paths:
        sys.stdout.write(f"{path}: ok\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
