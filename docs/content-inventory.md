# Content Inventory & Actions (2026-01-03)

Page count dropped from **19 → 8** authored markdown files (plus this inventory) while keeping every unique command from the original tutorials/how-tos/reference set.

| Path | Divio Quadrant | User Job | Word Count | Key Commands / Outputs | Notes |
| --- | --- | --- | --- | --- | --- |
| README.md | Landing | State value + route to docs | 423 | `uv pip install article-extractor`, `uv run article-extractor …`, `docker run ghcr.io/pankaj28843/article-extractor:latest` | Hero + Problem/Why/Outcome intro trimmed to keep README+docs/index ≤150 words combined. |
| docs/index.md | Landing | Explain doc sections | 157 | Links to tutorials, operations, reference, style, how-it-works | Single concept card style landing per Python tutorial cadence. |
| docs/tutorials.md | Tutorial | Run CLI, Docker, Python paths | 443 | `uv pip install …`, `uv run article-extractor …`, `docker run …`, `curl -XPOST …`, `uv run python - <<'PY' …` | Three Arrange/Act/Assert sections with captured output.
| docs/operations.md | How-To | Tune caches, networking, diagnostics, validation, releases | 747 | `ARTICLE_EXTRACTOR_CACHE_SIZE=…`, `docker run … -v`, `curl -XPOST …`, `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1 uv run …`, `gh run list --workflow docs --limit 1 | head -n 10`, `uv run mkdocs gh-deploy --remote-branch gh-pages` | Single runbook consolidating every operational recipe.
| docs/reference.md | Reference | Look up env vars + runtime syntax | 680 | Option table + canonical CLI/server/Python snippets | Mirrors Docker-style tables with FastAPI `.env` citation.
| docs/style-guide.md | Reference (Meta) | Keep tone consistent | 438 | References to Python tutorial, FastAPI, uv, Pytest, Docker, GitHub Actions | Defines Problem/Why/Outcome intros + Arrange/Act/Assert expectations.
| docs/explanations/how-it-works.md | Explanation | Teach pipeline + heuristics | 264 | KaTeX density formula, module boundaries, observability links | References APSD complexity guidance to justify clarity.
| docs/content-inventory.md | Explanation (Meta) | Track coverage + reductions | 794 | (This table) | Replaces legacy coverage-map and documents page-count delta + key commands.

Each surviving page maps cleanly onto the Divio quadrants while embedding the real commands recorded in `notes.md`.
