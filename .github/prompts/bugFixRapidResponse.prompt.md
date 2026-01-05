---
name: bugFixRapidResponse
description: Minimal, surgical fix for a reported defect with focused validation.
argument-hint: file="src/article_extractor/extractor.py" repro="steps" tests="test_extractor"
---

## TechDocs Research
Use `#techdocs` to verify correct API usage for the buggy component. Key tenants: `python`, `pytest`, `fastapi`, `docker`. Always run `list_tenants` first, then `describe_tenant` to get optimal queries. See `.github/instructions/techdocs.instructions.md` for full usage guide.

## Principles
- Reproduce the bug first; capture logs, failing CLI invocations, or red tests.
- Keep the diff as small as possible—no opportunistic cleanups unless they unblock the fix.
- Follow `.github/copilot-instructions.md` (Prime Directives) and `.github/instructions/validation.instructions.md` (validation loop, smoke expectations).
- Run every Python-facing command through `uv run` so the managed `.venv` is on `sys.path` ([uv docs](https://docs.astral.sh/uv/concepts/projects/run/)).

## Steps
1. **Confirm scope**: Identify the exact entrypoints (library call, CLI command, FastAPI route) plus the HTML sample that triggers the bug.
2. **Add/extend a failing test** (preferred) or capture the failing command output (`uv run article-extractor …`, FastAPI trace, etc.).
3. **Patch**:
   - Respect module boundaries: extraction heuristics stay in `extractor.py`, fetch orchestration inside `fetcher.py`, env parsing inside `server.py`.
   - Use guard clauses and descriptive errors; never swallow exceptions unless we already log them upstream.
4. **Verify**:
   - `timeout 60 uv run pytest tests/ -v -k <test_name>` (targeted) followed by the full suite if behavior changed widely.
   - Re-run the original repro command (CLI, HTTP request, or Docker smoke). For container bugs execute `./scripts/docker-playwright-smoke.sh <tag> <url>` after rebuilding.
   - `uv run ruff check <edited files>`.
5. **Report**: Summarize root cause, fix, validation commands, and whether Playwright/httpx parity was affected.

## Output
- Focused diff + short explanation of the behavioral change.
- Updated/added test demonstrating the fix.
- Follow-up items only if truly blocking (e.g., new env var doc, Docker note).
