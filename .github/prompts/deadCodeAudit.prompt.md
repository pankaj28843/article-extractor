---
name: deadCodeAudit
description: Systematically identify dead/unused code in article-extractor with evidence-based removal.
argument-hint: focus="src/article_extractor/"
---

You are in feature-freeze mode. Analyze, document, and remove dead or no-longer-relevant code with full validation coverage.

## Goal
Identify, document, and eliminate dead code in the target area with proof that the change is safe. "Relevant" means reachable from library/CLI/server behavior. Test-only helpers or dev scripts do **not** keep production code alive.

## Critical Commands (NEVER SKIP)
- `uv run ruff format .`
- `uv run ruff check --fix .`
- `timeout 60 uv run pytest tests/ -v`
- `uv run article-extractor --help`
- `uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia`
- `docker build -t article-extractor:test .`
- `./scripts/docker-playwright-smoke.sh article-extractor:test https://example.com/demo` (when touching Playwright/network/Docker code)

## Workflow

### 0. Pinned Directives
- Follow `.github/copilot-instructions.md` (minimal code, no backward compatibility, green-before-done).
- See `.github/instructions/software-engineering-principles.instructions.md` for module boundaries.
- Do **not** delete user-facing behaviors without updating README/notes if applicable.

### 1. Evidence Pass
1. Capture `git status -sb`.
2. Run `uv run vulture src/article_extractor --min-confidence 60` and list flagged symbols.
3. Run `uv run ruff check --select F401,F841 src/article_extractor` for unused imports/vars.
4. Use `rg -n "SYMBOL" src/article_extractor` (or `list_code_usages`) to confirm reachability.

### 2. Living PRP Plan
- Create/update `.github/ai-agent-plans/{date}-dead-code-plan.md` using the template in `.github/instructions/PRP-README.md`.
- Log discoveries, decisions, and scope adjustments as you go. No retroactive fill-ins.

### 3. Map Entrypoints & Dependencies
- Enumerate library entrypoints (`extract_article`, `ExtractionResult`), CLI commands, FastAPI routes, and Docker scripts.
- Trace import chains to ensure flagged code is not indirectly registered (fastapi dependency injection, CLI click commands, etc.).

### 4. Candidate Confirmation
- For each candidate capture: exact path::symbol, tool evidence (vulture/ruff), `rg` output, and explanation of why it is safe to delete.
- Prefer small, high-confidence batches. Move uncertain cases to "Open Questions" in the plan.

### 5. Execute Deletions
- Remove code rather than stub/`pass`. Delete unused tests + fixtures alongside the code.
- Clean up imports, type hints, docs, and CLI help referencing the removed symbols.
- If deleting env vars or settings, update README/notes + server docs immediately.

### 6. Validation Loop (Run After Each Batch)
1. `uv run ruff format .`
2. `uv run ruff check --fix .`
3. `get_errors` on touched Python files
4. `timeout 60 uv run pytest tests/ -v`
5. `uv run article-extractor --help`
6. `uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia`
7. `docker build -t article-extractor:test .`
8. `./scripts/docker-playwright-smoke.sh article-extractor:test https://example.com/demo`

Re-run from step 1 if any command fails.

### 7. Reporting & Plan Output
- Update the PRP plan with:
  - Executive summary (symbols removed, LOC saved, affected modules)
  - Evidence table (tool output + reasoning)
  - Validation log (actual commands + results)
  - Open questions needing review
- Reference files using workspace-relative paths (`src/article_extractor/fetcher.py`).

## Important Rules
1. Do not skip plan updates or evidence capture.
2. Never revert user changes; work on top of current HEAD.
3. Batch diffs narrowly—prefer many small deletions over one giant sweep.
4. Treat runtime decorators, FastAPI dependencies, and CLI entrypoints as potentially dynamic; confirm before deleting.
5. Remove associated tests/fixtures to avoid orphaned coverage.
6. If uncertain, park the candidate in "Open Questions" instead of deleting.

## Anti-Patterns to Avoid
- Deleting code used via dynamic imports or FastAPI dependency injection without checking `server.py` wiring.
- Skipping the Docker smoke test when Playwright/httpx code was touched.
- Leaving TODOs or commented-out blocks instead of removing them entirely.
- Collapsing planning + execution into one step; the PRP must exist **before** deletions begin.
