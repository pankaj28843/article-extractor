---
name: featureSliceDelivery
description: Implement a vertical slice (library/service/CLI/tests/docs) for a new capability.
argument-hint: feature="short name" scope="files or modules" verification="command"
---

## TechDocs Research
Use `#techdocs` to validate patterns before implementation. Key tenants: `python`, `fastapi`, `pytest`, `docker`. Always run `list_tenants` first, then `describe_tenant` to get optimal queries. See `.github/instructions/techdocs.instructions.md` for the full workflow.

## Ground Rules
- Start from a plan (run `prpPlanOnly` if one does not exist). Break delivery into thin commits.
- Keep entrypoints thin: CLI/server delegate to extractor + fetcher modules.
- Reuse shared utilities (FetchPreferences, ExtractionResult). Avoid bespoke env flags or ad-hoc httpx clients.

## Delivery Flow
1. **Context sync** – Read existing modules/services and note dependencies + env settings.
2. **Design mini blueprint** – Outline data shape, CLI args/FastAPI payloads, and tests before coding.
3. **Implement in layers** (validate between layers):
   - Library changes (`extractor.py`, `fetcher.py`, helpers in `utils.py`).
   - Service surface (FastAPI routes in `server.py`, CLI flags in `cli.py`).
   - Docs (README sections, notes) plus examples.
4. **Documentation** – Determine Divio quadrant:
   - Tutorial for end-to-end experiences
   - How-To for focused recipes
   - Reference for new CLI/env options
   - Explanation for architectural changes
   Update README/docs + navigation as needed.
5. **Validation** – Minimum commands:
   - `uv run ruff format .`
   - `uv run ruff check --fix .`
   - `timeout 60 uv run pytest tests/ -v`
   - `uv run article-extractor --help`
   - Run any new CLI/server flows end-to-end
   - If Docker-impacting: `docker build -t article-extractor:test .` and `./scripts/docker-playwright-smoke.sh article-extractor:test https://example.com/demo`

## Output
- Summary of scope + files touched per layer.
- Commands run with outcomes (include Docker smoke when applicable).
- Follow-up checklist (docs, release notes) if any.
