---
name: prpPlanOnly
description: Produce a Product Requirement Prompt (PRP) plan without touching code until explicitly approved.
argument-hint: brief="one-line objective" scope="files/domains in play"
---

## TechDocs Research
Use `#techdocs` to ground every assertion. Prioritize `python`/`pytest` (best practices), `fastapi` (HTTP server), `docker` (containerization), and `github-platform` (automation). Run `list_tenants` to discover additional documentation sources. Reference `.github/instructions/techdocs.instructions.md` for the full workflow.

## Mission
- Draft or update a PRP aligned with `.github/instructions/PRP-README.md`.
- Stay in planning mode: no code edits, migrations, env changes, or tests until stakeholders approve.

## Required Sections
1. **Goal / Why / Success Metrics** – tie back to measurable outcomes (Playwright parity, extraction accuracy, docs completeness).
2. **Current State** – cite concrete files/lines (README env vars, Dockerfile install steps, failing tests, etc.).
3. **Implementation Blueprint** – phased work packages mapped to files/scripts with TechDocs evidence.
4. **Context & Anti-Patterns** – highlight guardrails from `.github/instructions/software-engineering-principles.instructions.md` and `.github/copilot-instructions.md`.
5. **Validation Loop** – commands per phase: `uv run ruff format .`, `uv run ruff check --fix .`, `timeout 60 uv run pytest tests/ -v`, `uv run article-extractor --help`, optional Docker smoke.
6. **Open Questions & Risks** – blockers, missing data, approvals needed.

## Process
- Inventory facts before conclusions: read relevant modules, scripts, notes, and TechDocs references.
- Cite TechDocs URLs/snippets plus repo paths for every architectural claim.
- Keep bullets crisp; prefer ASCII tables for blueprint + evidence matrices.
- End with a readiness statement ("Ready to implement", "Need answer on storage state", etc.).

## Output
- Save or update the plan under `.github/ai-agent-plans/{date}-{slug}-plan.md`.
- Final response must recap key updates, link to the plan file, and list unresolved questions/approvals before coding.
