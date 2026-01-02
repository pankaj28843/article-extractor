---
applyTo: "src/article_extractor/**"
---

# article-extractor Engineering Principles

**Audience**: Contributors touching `src/article_extractor` (library, CLI, server, Docker wiring).  
**Purpose**: Capture the house rules for keeping extraction code simple, deterministic, and container-ready.

## Simplicity Over Patterns
- Favor one deep module over layers of helpers. If an abstraction does not delete duplication, delete the abstraction.
- Default to composition. New booleans or kwargs only ship after two concrete call sites demand different behavior.
- Measure refactors by reduced change amplification. If a feature edit spans extractor + fetcher + server for the same concept, redesign the boundary before merging.
- Remove pass-through functions. Every exported helper enforces an invariant (parse, normalize, score) or it gets inlined.

## Module Boundaries
- `extractor.py` owns scoring + Markdown conversion. Do not import FastAPI, Playwright, or httpx here.
- `fetcher.py` orchestrates network transport. Reuse `_fetch_with_httpx()` / `_fetch_with_playwright()`; never fork new fetch paths.
- `network.py` centralizes httpx configuration (timeouts, retries, proxy support). Extend it instead of instantiating raw clients elsewhere.
- `server.py` wires FastAPI routes and handles env parsing (`ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT`, `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE`). Surface typed settings via the `Settings` dataclass rather than exporting raw env access.
- `cli.py` stays thin: parse args, call `extract_article()`, print results.

## Playwright & Storage Guardrails
- Chromium install happens in the Dockerfile via `playwright install --with-deps --only-shell chromium`. Keep browser paths under `PLAYWRIGHT_BROWSERS_PATH` to avoid duplication.
- Honor `ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT` / `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE` across CLI and server. No new env flags unless the existing settings object cannot represent the use case.
- `FetchPreferences` is the extension point for headed vs httpx-only fetches. Add fields there instead of sprinkling booleans.

## CLI, Server, and Library Parity
- `extract_article()` is the canonical entrypoint. Both CLI and FastAPI routes must call it instead of replicating extraction logic.
- Validation endpoints belong in `server.py`; keep CLI purely synchronous/terminal friendly.
- Never let CLI/server mutate global extractor state. All configuration flows through explicit parameters, dataclasses, or dependency injection via FastAPI.

## Docker & Scripts
- Docker image builds must leave Chromium ready without extra steps. If a change requires new system deps, update the Dockerfile comments + README instructions at the same time.
- `scripts/docker-playwright-smoke.sh` (and future scripts under `scripts/`) are the only approved automation entrypoints. Keep them POSIX-sh compliant, `set -euo pipefail`, and re-run per `.github/instructions/validation.instructions.md`.

## Testing Expectations
- Unit tests live beside the behavior they cover (`tests/test_extractor.py`, `tests/test_fetcher.py`, etc.).
- Mock only external boundaries (httpx/Playwright). Prefer fixture inputs and recorded HTML over monkeypatching internals.
- Always add tests in the same PR as the behavior change. Async tests must use `pytest.mark.asyncio` and avoid sleeps—patch the network boundary instead.

## Documentation Hooks
- README sections describing Docker usage must cite official Docker docs through TechDocs (#techdocs `docker`). Run every command you document and paste real output.
- Keep troubleshooting tips in README/notes.md up to date whenever you touch Playwright, env parsing, or CLI error handling.

## Naming & Comments
- Names broadcast purpose (`FetchPreferences`, `ExtractionResult`). Avoid suffixes like Helper/Manager unless the type actually owns lifecycle.
- Comment intent, not mechanics. Explain why heuristics exist (e.g., density thresholds), not how loops work.
- Delete stale comments as soon as the code renders them obvious. Promotion-worthy rationale belongs in this file or notes.md, not inline forever.

## Validation is Non-Negotiable
- A change touching `src/article_extractor/**`, Dockerfile, or scripts is incomplete until the commands in `.github/instructions/validation.instructions.md` pass (lint → tests → CLI → Docker smoke).
- When headed-mode behavior changes, run `./scripts/docker-playwright-smoke.sh article-extractor:test https://example.com/demo` and capture results in the PR/notes.
