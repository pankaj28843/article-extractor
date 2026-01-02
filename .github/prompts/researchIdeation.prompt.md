---
name: researchIdeation
description: Explore solution options using TechDocs + repo intel before deciding on code changes.
argument-hint: topic="Playwright fetch reliability" focus="src/article_extractor/fetcher.py"
---

## TechDocs Research (Primary Focus)
This prompt centers on `#techdocs` exploration. Prioritize tenants based on the question: `python` for language features, `fastapi` for server patterns, `pytest` for testing, `docker` for container concerns, `github-platform` for automation. Run `list_tenants` first to discover documentation sources. Follow `.github/instructions/techdocs.instructions.md` for the workflow.

## Goals
- Clarify the problem, constraints, and possible approaches before coding.
- Surface prior art inside this repo (modules, tests, README) plus TechDocs evidence.
- End with actionable recommendations (next prompt to run, risks, approvals needed).

## Workflow
1. **Inventory sources** – `mcp_techdocs_list_tenants()` → `mcp_techdocs_describe_tenant()` for relevant tenants.
2. **Search smart** – Run focused `mcp_techdocs_root_search` queries. Fetch high-signal documents and capture URL + snippet references.
3. **Repo sweep** – Use `file_search`, `grep_search`, or targeted `read_file` calls to collect concrete references (paths + line ranges) inside `src/article_extractor/` and README/notes.
4. **Synthesize** – Organize findings into options (status quo, incremental refactor, new feature slice, spike). Highlight dependencies, env vars, and cite files + TechDocs references.
5. **Recommend next action** – Choose the follow-up prompt (bugFixRapidResponse, featureSliceDelivery, cleanCodeRefactor, prpPlanOnly, testHardening, etc.) and list prerequisites or approvals.

## Output
- Narrative covering problem recap → research findings → recommendation, with inline links to repo paths and TechDocs references.
- Bullet list of supporting evidence (TechDocs URLs + repo files/lines).
- Open questions or risks clearly flagged. No code/test changes.
