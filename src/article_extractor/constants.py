"""Constants for article extraction scoring.

Derived from Readability.js and Postlight Parser algorithms.
These constants are used by the scorer to identify content vs boilerplate.
"""

import re

# === TAG SCORING ===
# From Readability.js and Postlight Parser tag scoring
TAG_SCORES: dict[str, int] = {
    # Positive (content containers)
    "div": 5,
    "article": 5,
    "section": 5,
    "main": 5,
    "pre": 3,
    "blockquote": 3,
    "td": 3,
    "p": 0,  # Paragraphs scored separately
    "span": 0,  # Neutral - no impact
    # Negative - navigation and boilerplate elements
    "form": -3,
    "ol": -3,
    "ul": -3,
    "dl": -3,
    "dd": -3,
    "dt": -3,
    "li": -3,
    "address": -3,
    # Strongly negative
    "h1": -5,
    "h2": -5,
    "h3": -5,
    "h4": -5,
    "h5": -5,
    "h6": -5,
    "th": -5,
}

# Tags to score for content (Readability DEFAULT_TAGS_TO_SCORE)
SCORABLE_TAGS: set[str] = {"section", "h2", "h3", "h4", "h5", "h6", "p", "td", "pre"}

# === UNLIKELY CANDIDATES ===
# From Readability.js REGEXPS.unlikelyCandidates and Postlight UNLIKELY_CANDIDATES_BLACKLIST
UNLIKELY_CANDIDATES: list[str] = [
    "ad-break",
    "adbox",
    "advert",
    "addthis",
    "agegate",
    "aux",
    "banner",
    "breadcrumb",
    "combx",
    "comment",
    "community",
    "cookie",
    "disqus",
    "extra",
    "footer",
    "gdpr",
    "header",
    "hidden",
    "legends",
    "menu",
    "menubar",
    "meta",
    "mw-jump",
    "nav",
    "navigation",
    "newsletter",
    "outbrain",
    "pager",
    "pagination",
    "popup",
    "privacy",
    "promo",
    "rail",
    "related",
    "remark",
    "rss",
    "share",
    "shoutbox",
    "sidebar",
    "skyscraper",
    "social",
    "sponsor",
    "subscribe",
    "taboola",
    "teaser",
    "toolbar",
    "tweet",
    "twitter",
    "widget",
    "yom-remote",
]
UNLIKELY_CANDIDATES_RE: re.Pattern[str] = re.compile("|".join(UNLIKELY_CANDIDATES), re.IGNORECASE)

# Whitelist that overrides unlikely candidates
OK_MAYBE_CANDIDATES: list[str] = [
    "and",
    "article",
    "body",
    "blogindex",
    "column",
    "content",
    "entry",
    "hentry",
    "main",
    "page",
    "posts",
    "shadow",
]
OK_MAYBE_RE: re.Pattern[str] = re.compile("|".join(OK_MAYBE_CANDIDATES), re.IGNORECASE)

# === POSITIVE SCORE HINTS ===
# From Readability.js REGEXPS.positive and Postlight POSITIVE_SCORE_HINTS
POSITIVE_SCORE_HINTS: list[str] = [
    "article",
    "articlecontent",
    "blog",
    "body",
    "content",
    "entry",
    "hentry",
    "h-entry",
    "main",
    "page",
    "pagination",
    "post",
    "story",
    "text",
    r"[-_]copy",
    r"\Bcopy",  # usatoday pattern
]
POSITIVE_SCORE_RE: re.Pattern[str] = re.compile("|".join(POSITIVE_SCORE_HINTS), re.IGNORECASE)

# === NEGATIVE SCORE HINTS ===
# From Readability.js REGEXPS.negative and Postlight NEGATIVE_SCORE_HINTS
NEGATIVE_SCORE_HINTS: list[str] = [
    "-ad-",
    "hidden",
    r"^hid$",
    r" hid$",
    r" hid ",
    r"^hid ",
    "banner",
    "combx",
    "comment",
    "com-",
    "contact",
    "disqus",
    "extra",
    "foot",
    "footer",
    "footnote",
    "gdpr",
    "header",
    "legends",
    "masthead",
    "media",
    "meta",
    "nav",
    "outbrain",
    "pager",
    "popup",
    "promo",
    "related",
    "remark",
    "rss",
    "share",
    "shoutbox",
    "sidebar",
    "skyscraper",
    "sponsor",
    "taboola",
    "teaser",
    "widget",
]
NEGATIVE_SCORE_RE: re.Pattern[str] = re.compile("|".join(NEGATIVE_SCORE_HINTS), re.IGNORECASE)

# Photo hints (keep images in content)
PHOTO_HINTS: list[str] = ["figure", "photo", "image", "caption"]
PHOTO_HINTS_RE: re.Pattern[str] = re.compile("|".join(PHOTO_HINTS), re.IGNORECASE)

# Readability publisher guidelines asset class
READABILITY_ASSET_RE: re.Pattern[str] = re.compile(r"entry-content-asset", re.IGNORECASE)

# === THRESHOLDS ===
MIN_CHAR_THRESHOLD: int = 500  # Minimum chars for valid article
MIN_PARAGRAPH_LENGTH: int = 25  # Skip paragraphs shorter than this
MIN_WORD_COUNT: int = 150  # Minimum words for valid extraction
TOP_CANDIDATES_COUNT: int = 5  # Number of top candidates to consider
LINK_DENSITY_THRESHOLD: float = 0.25  # Max link density for content div

# === ROLES TO REMOVE ===
# From Readability.js UNLIKELY_ROLES
UNLIKELY_ROLES: list[str] = [
    "menu",
    "menubar",
    "complementary",
    "navigation",
    "alert",
    "alertdialog",
    "dialog",
]

# === BYLINE DETECTION ===
BYLINE_RE: re.Pattern[str] = re.compile(r"byline|author|dateline|writtenby|p-author", re.IGNORECASE)

# === COMMA PATTERN FOR CONTENT SCORING ===
COMMA_RE: re.Pattern[str] = re.compile(r",\s*")

# === TAGS TO PRESERVE ===
# Tags that should be preserved in content extraction
PRESERVE_TAGS: set[str] = {
    "a",
    "abbr",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "figcaption",
    "figure",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "q",
    "s",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

# === TAGS TO STRIP ===
# Tags that should be completely removed (with content)
STRIP_TAGS: set[str] = {
    "aside",
    "footer",
    "form",
    "header",
    "nav",
    "noscript",
    "script",
    "style",
    "svg",
}
