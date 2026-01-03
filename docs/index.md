# Article Extractor Documentation

Article Extractor ships a Pure-Python library, CLI, and FastAPI service for extracting the primary content block from arbitrary HTML. This site now houses the end-to-end tutorials, operational drilldowns, and reference guides so the README can focus on the elevator pitch.

## How to Use This Site

- **Tutorials** walk through CLI, Docker, and Python entry points end-to-end.
- **How-To Guides** focus on targeted jobs like overriding caches, configuring proxies, or tuning Playwright storage queues.
- **Reference** sections enumerate environment variables, CLI arguments, and API types.
- **Explanations** document the scoring pipeline, cache design, and reliability trade-offs.
- **Contributing & Release Engineering** clarify validation loops, GitHub CLI expectations, and Pages automation.

Each section follows the structure defined in [notes.md lines 29-130](https://github.com/pankaj28843/article-extractor/blob/main/notes.md#L29-L130): every page lists prerequisites, time-to-complete, and verification cues so operators can trust what they read.

Need to map a scenario to the right page? Check the [Documentation Coverage Map](coverage-map.md) for a MECE index of personas, goals, and canonical sources.

## What to Read First

- New users: start with the [CLI](tutorials/cli.md), [Docker](tutorials/docker.md), or [Python](tutorials/python.md) tutorials.
- Operators: jump to [Override Cache & Playwright Storage](how-to/cache-playwright.md), [Networking Controls](how-to/networking.md), and [Diagnostics & Metrics](how-to/diagnostics.md).
- Architects: review [Configuration](reference/configuration.md), [Runtime Interfaces](reference/runtime.md), and the explanation pages for rationale.
- Contributors: follow the [Docs Contribution Guide](contributing/index.md) plus the [Development Workflow](contributing/development.md).
- Release managers: keep the [Shipping Checklist](release-engineering/index.md) handy for Pages + Docker automation.

Use `uv run mkdocs serve --dev-addr 127.0.0.1:4000` while authoring; the strict validation settings (from #techdocs mkdocs/user-guide/configuration.md) surface missing nav entries or anchors before CI fails.
