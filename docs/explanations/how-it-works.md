# How It Works

**Audience & Prereqs**: Engineers in the Explanation lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table) who want heuristic/architecture details; expect comfort with Python async patterns and the modules in `.github/instructions/software-engineering-principles.instructions.md`.

Article Extractor keeps heuristics inside `src/article_extractor/extractor.py`, with supporting modules (`fetcher.py`, `scorer.py`, `server.py`) following the deep-module guardrails outlined in `.github/instructions/software-engineering-principles.instructions.md`.

## Pipeline

1. **Parse HTML** with [JustHTML](https://github.com/EmilStenstrom/justhtml) to build a clean DOM-like tree.
2. **Strip noise** (scripts, nav, ads) before scoring candidates.
3. **Score blocks** using Readability-inspired signals (density, link ratio, structural hints). Density can be summarized as $density = text\_length / node\_area$ for intuition.
4. **Pick the winner** after normalizing headings and resolving relative links.
5. **Emit HTML and Markdown**, sanitizing output for downstream systems.
6. **Return metadata** (title, excerpt, warnings, author, timestamps) so clients can quickly inspect quality.

## Determinism

- Scoring has no randomness; identical HTML produces identical Markdown.
- Fetch preferences flow through `FetchPreferences` so CLI, server, and library stay in sync.
- Environment parsing lives in `server.py` to keep call sites typed and deterministic.

## Storage & Queueing

- Headed Playwright sessions write cookies to `storage_state.json` and queue deltas beside the file so multiple workers reuse authenticated sessions safely.
- Queue thresholds are configurable via env vars documented in the [Configuration Reference](../reference/configuration.md#playwright-storage-queue).

## Observability Hooks

- Structured logs surface request IDs, latency, cache hits, and queue metrics.
- Optional StatsD metrics report CLI/server throughput; see [Diagnostics & Metrics](../how-to/diagnostics.md).

For tutorials and configuration walkthroughs, jump to the [Tutorials landing page](../tutorials/index.md) or the [Reference section](../reference/index.md).
