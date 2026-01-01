---
name: bugFixRapidResponse
description: Minimal, surgical fix for a reported defect with focused validation.
argument-hint: file="src/article_extractor/extractor.py" repro="steps" tests="test_extractor"
---

## TechDocs Research
Use `#techdocs` to verify correct API usage for the buggy component. Key tenants: `python`, `fastapi`, `pytest`. Always run `list_tenants` first, then `describe_tenant` to get optimal queries. See `.github/instructions/techdocs.instructions.md` for full usage guide.

## Principles
- Reproduce the bug first; capture logs or failing tests.
- Keep the diff as small as possible—no opportunistic cleanups unless they unblock the fix.
- Follow `.github/copilot-instructions.md` (Prime Directives) and `.github/instructions/validation.instructions.md` (validation loop, test requirements).

## Steps
1. **Confirm scope**: Identify exact entrypoints (CLI command, function, etc.) and data involved.
2. **Add/extend a failing test** (preferred) or capture the failing command output.
3. **Patch**:
   - Use guard clauses, clear errors, and logging aligned with existing patterns.
4. **Verify**:
   - `uv run pytest tests/ -v -k <test_name>`
   - Any repro script originally failing.
   - `uv run ruff check <edited file>`
5. **Report**: Summarize root cause, fix, and validation commands run.

## Output
- Focused diff + brief explanation of behavioral change.
- Updated/added test demonstrating the fix.
- Follow-up items only if truly blocking (e.g., config change).
