---
name: iterativeCodeSimplification
description: Multiple fast passes to shrink logic, remove bloat, and harden resilience without obsessing over polish.
argument-hint: file="src/article_extractor/extractor.py" verify="uv run pytest tests/ -v -k extractor"
---

## TechDocs Research
Use `#techdocs` for simplification techniques, async patterns, and architecture guidance. Run `list_tenants` first, then explore tenants like `python`, `fastapi`, `docker`. Follow the workflow in `.github/instructions/techdocs.instructions.md`.

## Intent
- Reduce branching/LOC while keeping extraction output identical for all fixtures.
- Improve resilience by clarifying guard clauses, error surfacing, and fetch fallbacks.
- Naming/doc polish is optional—hand off to **cleanCodeRefactor** if semantics need a second pass.

## Scope Guardrails
- Touch only the files required for the optimization; list other opportunities in the final notes.
- Preserve CLI/server signatures and settings objects unless the user explicitly approved a breaking change.
- Keep async boundaries intact—no mixing sync and async helpers without a plan.

## Working Style
1. **Snapshot**: Capture quick metrics (LOC, branch count, cyclomatic complexity) before editing.
2. **Plan tiny passes**: Each iteration targets a single idea (flatten nested scoring loops, dedupe normalization, consolidate `FetchPreferences` checks, etc.).
3. **Research fast**: Use TechDocs and repo history for proven patterns (e.g., readability-like scoring, httpx retries).
4. **Edit**: Apply guard clauses, helper extraction, or data-class usage to shrink logic.
5. **Verify immediately**:
   - Run the supplied `verify` command (commonly `uv run pytest tests/ -v -k <area>`), then the full suite if behavior surfaces change widely.
   - `uv run ruff check <file>` after the final pass; format only the touched files.
6. **Log findings**: Track iteration-level deltas (LOC change, branch count, perf notes) in the response.

## Tactics
- Hoist repeated selectors/regexes into constants.
- Replace nested branching with guard clauses or early returns.
- Use comprehensions/dataclasses for candidate filtering when readability stays high.
- Collapse duplicated Playwright/httpx selection logic into shared helpers.

## Validation Checklist
- Run the supplied verify command after every iteration.
- `uv run pytest tests/ -v` once the sequence of edits ends.
- `uv run ruff check <file>` (and `uv run ruff format <file>` if indentation shifts).
- If Docker behavior or fetch preferences shift, rerun `./scripts/docker-playwright-smoke.sh` and note the output.

## Output
- Iteration table summarizing metric deltas, key simplifications, and verification status.
- Deferred cleanups (naming/docs) explicitly listed for follow-up prompts.
- Commands executed vs. pending clearly stated.
