# AGENTS.md (article-extractor)

## Scope
- Follow repository conventions in `.github/copilot-instructions.md` and CONTRIBUTING docs.
- Use JustHTML for parsing; do not introduce BeautifulSoup.
- Keep extraction logic centralized in `src/article_extractor/extractor.py`; keep CLI/server thin.

## Workflow
- Use `uv run` for all Python commands.
- Prefer small, surgical diffs; remove dead code instead of adding layers.
- Avoid hiding errors with broad `try/except`.
- Do not add summary reports unless explicitly requested.

## Validation
- Run: `uv run ruff format . && uv run ruff check --fix .`
- Run: `timeout 60 uv run pytest -v`
- Run: `uv run article-extractor --help`

## Planning
- Store PRP plans in `~/codex-prp-plans` (not in-repo).
- Update the plan after each phase; keep UTC timestamps with `Z` suffix.

## Privacy / Safety
- Do not include local machine details, IPs, or tenant-specific data in code or docs.
- Sanitize any real URLs before committing; use `example.com` placeholders.
