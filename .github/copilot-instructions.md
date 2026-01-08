# AI Coding Agent Instructions for article-extractor

> **For AI contributors only** – these guardrails extend the README and contributor docs.

**Project Context**: Article Extractor ships a pure-Python library, CLI, and FastAPI service that detect the main content block in arbitrary HTML. We lean on JustHTML parsing, Readability-style scoring, and optional Playwright-powered fetchers so the Docker image can capture paywalled or JS-heavy pages out of the box.

## Core Philosophy

**NO BACKWARD COMPATIBILITY** – Break API/CLI/server behavior whenever it makes the extractor better. Only preserve old flows if the user explicitly asks.
**MINIMAL CODE** – Prefer small, surgical diffs. Delete abstractions unless they actively remove duplication.
**RESILIENT BUT TRANSPARENT** – Handle expected I/O failures (HTTP timeouts, Chromium not installed) but never hide stack traces behind blanket `try/except` blocks.
**GREEN TESTS ALWAYS** – Every branch of the validation loop must pass before handing off work. Fix, update, or delete failing tests immediately.
**NO SUMMARY REPORTS** – Skip retrospective write-ups unless the user asks for them.

## Design Principles for Extraction Simplicity

- **Deep modules, thin edges** – `extractor.py` owns candidate scoring, `fetcher.py` owns HTTP/Playwright orchestration, and `server.py` only maps FastAPI routes to those modules. Keep each module deep instead of layering helpers.
- **Information hiding** – Environment parsing (e.g., `ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT`, `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE`) stays inside `server.py`/`network.py`. Callers receive typed settings, not raw env lookups.
- **Composition over configuration** – Reuse the existing `FetchPreferences` dataclass rather than adding one-off boolean webs or ad-hoc kwargs.
- **CLI ≠ server** – The CLI, HTTP service, and library share the same extractor API. Never duplicate extraction logic in entrypoints; call `extract_article()` and let it orchestrate the flow.
- **Deterministic scoring** – Keep heuristics pure and side-effect free. All randomness belongs in tests, never the library.

## Runtime Guardrails

- `src/article_extractor/extractor.py` is the canonical content detector. Only change scoring rules there and add tests in `tests/test_extractor.py`.
- `src/article_extractor/fetcher.py` mediates between httpx + Playwright. Reuse `_fetch_with_httpx`/`_fetch_with_playwright` instead of creating parallel fetch paths.
- `src/article_extractor/network.py` owns shared HTTP settings (timeouts, retry policies). Extend the helper instead of sprinkling new httpx clients across the codebase.
- `src/article_extractor/server.py` is the only place that taps environment variables or FastAPI wiring. Add new settings by extending `_prefer_playwright()` and the `Settings` dataclass.
- `Dockerfile` already installs Chromium in the final stage (`playwright install --with-deps --only-shell chromium`). Do not add alternate install scripts; adjust build args or documentation if behavior needs to change.
- `scripts/docker-playwright-smoke.sh` (once introduced) is the authoritative container test. Keep smoke coverage in sync with validation instructions.

## Prime Directives

- Use `uv run` for every Python command (`uv run pytest`, `uv run article-extractor`, `uv run uvicorn …`).
- Stay in planning mode until the user approves when operating under `prpPlanOnly`.
- **Green-before-done**: no completion message until formatting, linting, tests, and required smoke checks all pass.
- Never hallucinate paths, env vars, or commands. Inspect the repo first.
- TechDocs-first research before touching files (workflow below).
- When documenting commands, run them and paste the actual output. Never fabricate terminal screenshots or log excerpts.

## TechDocs Research Workflow

1. `mcp_techdocs_list_tenants()` – enumerate available doc sources.
2. `mcp_techdocs_describe_tenant(codename="...")` – capture context and sample queries.
3. `mcp_techdocs_root_search(tenant_codename="...", query="...")` – find the relevant section.
4. `mcp_techdocs_root_fetch(tenant_codename="...", uri="...")` – quote the authoritative guidance.

**Priority tenants**: `python`, `pytest`, `fastapi`, `docker`, `github-platform`. Full process documented in `.github/instructions/techdocs.instructions.md`.

## Validation & Testing

Follow the mandatory loop from `.github/instructions/validation.instructions.md` after every code change (including Docker or script edits):

```bash
uv run ruff format .
uv run ruff check --fix .
timeout 60 uv run pytest tests/ -v
timeout 60 uv run pytest tests/ --cov=src/article_extractor --cov-report=term-missing --cov-fail-under=95
uv run article-extractor --help
```

For Docker/Playwright work, extend the loop with:

```bash
docker build -t article-extractor:test .
./scripts/docker-playwright-smoke.sh article-extractor:test https://example.com/demo
```

## Testing Rules

- Add/extend tests in `tests/` alongside every behavior change. Favor fixtures already defined in `tests/conftest.py`.
- Prefer behavioral assertions (extractor output, server response) rather than mocking internals.
- Async tests use `pytest.mark.asyncio`; keep them deterministic by mocking network layers instead of sleeping.
- Minimum unit test coverage: 95% (target near-100% with MECE tests). Coverage failures must fail CI on PRs and `main`.
- See `.github/instructions/tests.instructions.md` for all pytest conventions.

## URL Hygiene (CRITICAL)

**Never leak user-specific URLs into code, tests, or documentation.**

When debugging with real URLs (e.g., internal wikis, company Confluence spaces):

1. **Use editable install for local debugging**:
   ```bash
   uv tool install --editable --force --refresh --reinstall ".[all]"
   article-extractor https://internal.company.com/real/page
   ```

2. **Before committing, sanitize all URLs**:
   - Replace internal hostnames with `example.com`, `wiki.example.com`, etc.
   - Replace identifiable path segments (project codes, page IDs, names) with generic placeholders
   - Use patterns like: `DOCS`, `12345678`, `GettingStarted`, `post-1`

3. **Forbidden patterns in committed code**:
   - ❌ Real company domains (e.g., `*.corp.com`, `*.internal.net`)
   - ❌ Internal project codes (e.g., `PROJ-123`, `TEAM-456`)
   - ❌ Identifiable page names or IDs from real systems
   - ❌ Any URL you wouldn't want public

4. **Allowed patterns**:
   - ✅ `example.com`, `wiki.example.com`, `docs.example.com`
   - ✅ `en.wikipedia.org` (public, stable)
   - ✅ Generic placeholders: `DOCS`, `12345678`, `GettingStarted`

5. **Pre-commit check**: Before staging, run:
   ```bash
   git diff --cached | grep -iE "(confluence|internal|corp\.|\.net/)" && echo "⚠️  Check for leaked URLs"
   ```

## Documentation & Verification

- Run every documented CLI/server command before editing README/notes. Paste real output blocks.
- Reference Docker env/volume flags via official docs: `docker container run --env/--volume` (#techdocs `docker`).
- Tutorials/how-tos must declare prerequisites, time estimates, and verification steps.

## Planning & Memory

- Non-trivial efforts require a PRP stored at `.github/ai-agent-plans/{ISO-timestamp}-{slug}-plan.md` (template in `.github/instructions/PRP-README.md`).
- Update the plan as scope evolves; never retrofit it after coding.

## Prompt Library (Article Extractor Editions)

All prompts live under `.github/prompts/` and reference these instructions:

- `prpPlanOnly.prompt.md` – Planning mode (no code edits).
- `researchIdeation.prompt.md` – TechDocs-first exploration before coding.
- `featureSliceDelivery.prompt.md` – Vertical slice from extractor changes down to server + docs.
- `bugFixRapidResponse.prompt.md` – Surgical bug fixes with focused validation.
- `cleanCodeRefactor.prompt.md` – Naming/structure cleanup without behavior changes.
- `iterativeCodeSimplification.prompt.md` – Repeated passes to shrink logic safely.
- `deadCodeAudit.prompt.md` – Identify and remove unused code paths.
- `testHardening.prompt.md` – Add or improve coverage without touching production logic.
- `coverageHandoff.prompt.md` – Continue a multi-iteration coverage push using shared plans.
- `docsRewrite.prompt.md` – Full rewrites aligned to Divio quadrants.
- `alignDocsSection.prompt.md` – Surgical section fixes.
- `docsRealityCheck.prompt.md` – Verify docs by running every command.
- `commentIntentAudit.prompt.md` – Trim comment noise, keep only intent.
- `visualDocsQA.prompt.md` – Screenshot MkDocs output and inspect with vision.

## Path-Specific Instructions

| Pattern | File | Purpose |
|---------|------|---------|
| `**/*.py`, `pyproject.toml` | [validation.instructions.md](instructions/validation.instructions.md) | Validation commands + Docker smoke expectations |
| `tests/**/*.py` | [tests.instructions.md](instructions/tests.instructions.md) | Pytest + coverage standards |
| `.github/ai-agent-plans/**` | [PRP-README.md](instructions/PRP-README.md) | Planning format |
| GitHub CLI usage | [gh-cli.instructions.md](instructions/gh-cli.instructions.md) | Non-interactive `gh` patterns |
| Core modules (`src/article_extractor/**`) | [software-engineering-principles.instructions.md](instructions/software-engineering-principles.instructions.md) | Deep-module guardrails |

## Key Files & Commands

```yaml
- file: src/article_extractor/extractor.py   # Candidate selection + Markdown output
- file: src/article_extractor/fetcher.py     # httpx + Playwright orchestration
- file: src/article_extractor/server.py      # FastAPI surface + env parsing
- file: src/article_extractor/cli.py         # CLI entry point (article-extractor command)
- file: Dockerfile                           # Chromium install + runtime image build
- dir: scripts/                              # Repo scripts (add docker smoke)
```

Baseline commands to keep handy:

```bash
uv run article-extractor --help
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia
uv run uvicorn article_extractor.server:app --reload --port 3000
docker build -t article-extractor .
docker run --rm -p 3000:3000 article-extractor
```

## Where to Learn More

- README.md – Contributor overview, env vars, Docker usage tips.
- notes.md – Scratchpad for ongoing investigations (keep it updated when running prompts like coverageHandoff).
- `.github/instructions/validation.instructions.md` – Full validation checklist including Docker smoke.
- `.github/instructions/software-engineering-principles.instructions.md` – Detailed design guardrails for extractor/fetcher/server layers.
