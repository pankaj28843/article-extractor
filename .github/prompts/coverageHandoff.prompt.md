---
name: coverageHandoff
description: Continue a multi-iteration coverage push, documenting progress and next steps.
argument-hint: planPath="tasks.md" target="src/article_extractor/extractor.py"
---

## TechDocs Research
Use `#techdocs` to ground testing patterns. Key tenants: `pytest`, `python`, `fastapi`. Follow `.github/instructions/techdocs.instructions.md` for the full workflow.

## Goals
- Resume a coverage push tracked in a shared markdown plan (argument `planPath`, default `notes.md`).
- Ensure anyone can pick up where you stop and move toward ≥90% overall coverage (per `.github/instructions/tests.instructions.md`).

## Workflow
1. **Load and respect the plan**
   - Read the referenced plan file fully before acting.
   - Capture iteration number, coverage snapshot, and remaining checklist items.
   - Never spawn a new plan unless the current one explicitly orders it.

2. **Honor the coverage loop**
   - Default command: `uv run pytest tests/ --cov=src/article_extractor --cov-report=term-missing` (optionally filtered per plan).
   - Anti-patterns: skipping timeout-wrapped runs when required, forgetting to update the plan, leaving failing tests behind.

3. **Record TechDocs evidence**
   - Before coding, run `mcp_techdocs_list_tenants`, `describe_tenant`, `root_search`, `root_fetch` for the tenant most aligned with the coverage focus (usually `pytest`).
   - Summarize takeaways in the plan or notes.

4. **Summarize current progress**
   - Report which files/tests improved, which commands ran, and any failures.
   - Note blockers, flaky suites, or tooling gaps so the next engineer inherits context.

5. **Plan the next iteration**
   - Point to remaining unchecked plan items, justify why they matter, and include commands to run next.

## Output
- Updated status summary tied back to `planPath` (include coverage numbers, commands, next actions).
- TechDocs-backed list of patterns/tools you referenced.
- Clearly call out remaining risks or questions.
