---
name: testHardening
description: Strengthen or add tests without touching production logic.
argument-hint: target="module or behavior" focus="unit|integration|async"
---

## TechDocs Research
Use `#techdocs` for testing patterns, fixtures, and mocking strategies. Key tenants: `pytest`, `python`, `fastapi`. Always run `list_tenants` first, then `describe_tenant` to get optimal queries. See `.github/instructions/techdocs.instructions.md` for full usage guide.

## Policies
- Obey `.github/instructions/tests.instructions.md` (no docstrings, `test_*` names, prefer fixtures over ad-hoc setup, async tests use `@pytest.mark.asyncio`).
- Mirror repo quality gates: keep helpers tiny, dedupe fixtures, maintain deterministic HTML fixtures under `tests/fixtures/` when possible.
- Never mock extractor internals; only mock external surfaces (network transport, filesystem, time) when isolation demands it.

## Steps
1. **Gap analysis** – Inventory behaviors missing coverage (edge cases, HTML quirks, concurrency boundaries, CLI/server glue).
2. **Test design** – Outline inputs/outputs, fixtures, and failure expectations. Prefer realistic HTML captured under `tests/data/`.
3. **Implement**:
   - Target behavior, not implementation: assert on extraction result fields, HTTP responses, CLI exit codes.
   - Use fixtures from `tests/conftest.py`; create new ones only when reuse is impossible.
   - Mock Playwright/httpx clients only at network boundaries; never stub scoring helpers.
4. **Validation**:
   - `timeout 60 uv run pytest tests/ -v -k <target>` for fast feedback.
   - `timeout 60 uv run pytest tests/ --cov=src/article_extractor --cov-report=term-missing` (aim for ≥90% overall, ~100% for new code).
   - `uv run ruff check <touched files>` when helper modules change.
5. **Report** – Capture coverage deltas, flaky cases, and any blind spots that remain.

## Output
- Summary of new cases and behaviors covered.
- Commands executed and their outcomes.
- Follow-up work (if any) for remaining coverage gaps.
