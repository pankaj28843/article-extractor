"""Title extraction for HTML documents.

Deep module that extracts page titles using cascading fallback strategies.
Hides OG meta, h1, title tag, and URL parsing complexity behind a simple interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from justhtml import JustHTML


def extract_title(doc: JustHTML, url: str = "") -> str:
    """Extract page title using cascading fallback strategies.

    Simple interface that hides meta tag parsing, DOM traversal, and URL manipulation.

    Tries in order:
    1. og:title meta property
    2. First h1 element text
    3. <title> tag (with suffix cleaning)
    4. URL path-derived title
    5. "Untitled" as final fallback

    Args:
        doc: JustHTML document to extract title from
        url: Optional URL for fallback title generation

    Returns:
        Extracted or generated title string

    Example:
        >>> title = extract_title(doc, "https://example.com/my-article")
    """
    # Try og:title
    og_title = doc.query('meta[property="og:title"]')
    if og_title:
        content = og_title[0].attrs.get("content", "")
        if content:
            return str(content)

    # Try first h1
    h1_nodes = doc.query("h1")
    if h1_nodes:
        h1_text = h1_nodes[0].to_text(strip=True)
        if h1_text:
            return h1_text

    # Try <title> tag
    title_nodes = doc.query("title")
    if title_nodes:
        title_text = title_nodes[0].to_text(strip=True)
        if title_text:
            # Clean common suffixes like " - Site Name"
            if " - " in title_text:
                title_text = title_text.split(" - ")[0].strip()
            return title_text

    # Fallback to URL
    url_title = _title_from_url(url)
    if url_title:
        return url_title

    return "Untitled"


def _title_from_url(url: str) -> str | None:
    """Build a readable title from a URL path.

    Extracts the last path segment and converts it to title case.
    Replaces hyphens and underscores with spaces.
    """
    if not url:
        return None

    path = urlparse(url).path
    if not path or path == "/":
        return None

    title = path.strip("/").split("/")[-1].replace("-", " ").replace("_", " ")
    return title.title()
