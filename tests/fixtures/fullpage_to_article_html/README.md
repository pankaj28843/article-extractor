# Full Page HTML -> Extracted Article HTML fixtures

Each fixture case contains:
- `raw.html`: full rendered page HTML fetched through `PlaywrightFetcher.fetch()`
- `expected.html`: expected article-focused HTML fragment (baseline for extraction assertions)
- `meta.json`: URL, source feed, status code, proxy, and extraction metadata

## Layout

- `tests/fixtures/fullpage_to_article_html/<host>/<case-slug>/raw.html`
- `tests/fixtures/fullpage_to_article_html/<host>/<case-slug>/expected.html`
- `tests/fixtures/fullpage_to_article_html/<host>/<case-slug>/meta.json`

Host folders represent the **original article website** (not the feed wrapper host).

## Source feeds sampled

- `feeds.feedburner.com/brainpickings/rss` (The Marginalian)
- `feeds.thelocal.com/rss/builder/dk` (The Local Denmark)
- `hnrss.org/newest?points=100&comments=25&count=25`
- `leaddev.com/feed`
- `rssproxy.pankajsingh.dev/.../martinfowler.com/...`
- `simonwillison.net/atom/everything/`
- `www.infoworld.com/feed/`
- `www.technologyreview.com/feed/`
- `world.hey.com/dhh/feed.atom`

## Formatting

- HTML is formatted for readability using 2-space indentation (Prettier where parseable).
- One legacy/malformed page (`jsomers.net`) is normalized with parser recovery and kept readable.

## Notes for expansion

- Add new cases under the relevant `<host>` folder.
- Keep `raw.html` as full page capture.
- Keep `expected.html` as the expected article area for comparison harnesses.
- Update `fixtures_index.json` after adding/removing cases.

## Test style

- Black-box only: load `raw.html`, run extractor, compare against `expected.html`.
- Comparison uses JustHTML text extraction and ignores whitespace differences.
- Keep test logic intentionally simple; extraction behavior changes should be handled in extractor code and fixtures.
