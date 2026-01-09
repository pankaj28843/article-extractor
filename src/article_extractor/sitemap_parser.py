"""Sitemap XML parsing and loading utilities.

Provides functions to parse XML sitemaps (both regular sitemaps and
sitemap indexes) and recursively load URLs from local files or remote URLs.
"""

from __future__ import annotations

import logging
from pathlib import Path

import defusedxml.ElementTree as ET

from .fetcher import Fetcher

logger = logging.getLogger(__name__)


def parse_sitemap_xml(xml_content: str) -> list[str]:
    """Extract URLs from sitemap XML (<urlset> or <sitemapindex>).

    Returns a list of URLs found in <loc> elements. For <sitemapindex>,
    returns the nested sitemap URLs (caller must fetch and parse them).
    """
    urls: list[str] = []
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        logger.warning("Failed to parse sitemap XML: %s", exc)
        return urls

    # Handle both namespaced and non-namespaced elements
    for loc in root.iter():
        tag_name = loc.tag.split("}")[-1] if "}" in loc.tag else loc.tag
        if tag_name == "loc" and loc.text:
            urls.append(loc.text.strip())

    return urls


def is_sitemap_index(xml_content: str) -> bool:
    """Check if the XML is a sitemapindex (contains nested sitemaps)."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return False

    tag_name = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    return tag_name == "sitemapindex"


async def load_sitemap(
    source: str,
    fetcher: Fetcher | None = None,
) -> list[str]:
    """Load URLs from a sitemap source (local file or remote URL).

    For sitemapindex files, recursively fetches nested sitemaps.
    Returns a flat list of all discovered page URLs.
    """
    if _is_local_path(source):
        return await _load_local_sitemap(source)
    return await _load_remote_sitemap(source, fetcher)


def _is_local_path(source: str) -> bool:
    """Determine if source is a local file path vs URL."""
    if source.startswith(("http://", "https://")):
        return False
    # Treat as local if it looks like a path
    return "/" in source or source.endswith(".xml") or Path(source).exists()


async def _load_local_sitemap(path: str) -> list[str]:
    """Read and parse a local sitemap file."""
    try:
        content = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read local sitemap %s: %s", path, exc)
        return []

    urls = parse_sitemap_xml(content)
    if is_sitemap_index(content):
        # Recursively load nested sitemaps (local files only)
        nested: list[str] = []
        for sitemap_url in urls:
            if _is_local_path(sitemap_url):
                nested.extend(await _load_local_sitemap(sitemap_url))
            else:
                logger.debug("Skipping remote sitemap in local index: %s", sitemap_url)
        return nested
    return urls


async def _load_remote_sitemap(
    url: str,
    fetcher: Fetcher | None,
) -> list[str]:
    """Fetch and parse a remote sitemap URL."""
    if fetcher is None:
        logger.warning("No fetcher provided for remote sitemap: %s", url)
        return []

    try:
        content, status = await fetcher.fetch(url)
    except Exception as exc:
        logger.warning("Failed to fetch sitemap %s: %s", url, exc)
        return []

    if status >= 400:
        logger.warning("Sitemap fetch returned status %s: %s", status, url)
        return []

    urls = parse_sitemap_xml(content)
    if is_sitemap_index(content):
        # Recursively fetch nested sitemaps
        nested: list[str] = []
        for sitemap_url in urls:
            nested.extend(await _load_remote_sitemap(sitemap_url, fetcher))
        return nested
    return urls
