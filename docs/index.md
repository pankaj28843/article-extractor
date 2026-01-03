# Article Extractor Documentation

> **Problem**: Documentation sprawled across 19 Markdown files, forcing readers to stitch together tutorials, how-tos, and references.  \
> **Why**: Following the Python tutorial and uv guides means each surface can open with a purpose-first paragraph and land a working command quickly.  \
> **Outcome**: Four sections—Tutorials, Operations, Reference, Explanations—each with Problem/Why/Outcome intros and Arrange/Act/Assert recipes.

## Pick a Job

- **Tutorials** ([tutorials.md](tutorials.md)) — CLI, Docker, and Python walkthroughs with command blocks and verification steps.
- **Operations** ([operations.md](operations.md)) — Cache tuning, networking, diagnostics, validation, and release automation in one runbook.
- **Reference** ([reference.md](reference.md)) — Env defaults, `.env` precedence, and canonical CLI/server/Python snippets.
- **How It Works** ([explanations/how-it-works.md](explanations/how-it-works.md)) — Pipeline overview, scoring math, and observability hooks.
- **Voice & Style** ([style-guide.md](style-guide.md)) — Tone rules, Problem/Why/Outcome expectations, and hero copy examples for contributors.

Use `uv run mkdocs serve --dev-addr 127.0.0.1:4000` while editing; strict nav/link validation (per #techdocs file:///home/pankaj/Personal/Code/docs-mcp-server/mcp-data/mkdocs/user-guide/writing-your-docs.md) fails fast when anchors or pages drift.
