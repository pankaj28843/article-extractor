---
name: cleanCodeRefactor
description: Targeted renaming and structure cleanup that keeps behavior stable and intent obvious.
argument-hint: path="src/article_extractor/" brief="optional short description"
---

## TechDocs Research
Use `#techdocs` for naming conventions, refactoring patterns, and architecture guidance. Run `list_tenants` first, then `describe_tenant` to discover available documentation sources (e.g., `python` for stdlib best practices, `fastapi` for HTTP patterns, `docker` for container tips). See `.github/instructions/techdocs.instructions.md` for full usage guide.

## When to Use
- The user asked for clearer names/structure without altering scoring or fetch semantics.
- Documentation expectations are already specified (default: leave docstrings alone unless they block understanding).
- Comments stay rare—prefer intent-revealing identifiers, fixtures, and helper names over prose.

## Guardrails from Repo Rules
- Follow `.github/copilot-instructions.md`: Core Philosophy + AI-bloat prevention.
- Respect `.github/instructions/software-engineering-principles.instructions.md` for module boundaries (extractor vs fetcher vs server).
- Validation loop lives in `.github/instructions/validation.instructions.md`; run it whenever code changes.
- Tests follow `.github/instructions/tests.instructions.md`.
- Keep diffs tight: avoid mass renames unless the user scoped them explicitly.

## Refactor Flow
1. **Scope check**: Confirm whether docstrings/comments change. Default to *code-only* updates.
2. **Research smartly**: Search repo & TechDocs for patterns (e.g., canonical `FetchPreferences` usage) before editing.
3. **Rename + reorganize**:
   - Swap cryptic symbols for descriptive names (`body`, `extraction_result`, etc.).
   - Inline pass-through helpers; extract helpers only when they delete duplication.
   - Keep heuristics pure; avoid mixing FastAPI/httpx concerns into extractor code.
4. **Usage sweep**:
   - Update all imports/call sites via `list_code_usages` or `grep_search`.
   - Keep public signatures stable unless the user approved a breaking change.
5. **Validation**:
   - `timeout 60 uv run pytest tests/ -v` for changed code paths.
   - `uv run ruff check <path>` (plus `uv run ruff format <path>` if whitespace moved).

## Output
- Summarize renames + structural edits and mention untouched docstrings if deferred.
- List commands executed; if something could not run, note the follow-up.
