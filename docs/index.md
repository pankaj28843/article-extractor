# Article Extractor Documentation

This site groups every public-facing detail for the CLI, FastAPI server, and Python API into four sections. Pick the page that matches your current task and copy the commands directly—each block was captured from a real session.

**Audience**: Engineers shipping ingestion pipelines, search, or automation that needs stable Markdown from HTML.  
**Prerequisites**: Python 3.12+ and a shell; Docker optional for server workflows.  
**Time**: ~5 minutes to find the right workflow.  
**What you'll get**: The fastest path to CLI, server, or library usage with verified commands.

## Pick a Job

- **Tutorials** ([tutorials.md](tutorials.md)) — CLI, Docker, and Python walkthroughs with command blocks and verification steps.
- **Operations** ([operations.md](operations.md)) — Cache tuning, networking, diagnostics, validation, and release automation in one runbook.
- **Reference** ([reference.md](reference.md)) — Env defaults, `.env` precedence, and canonical CLI/server/Python snippets.
- **How It Works** ([explanations/how-it-works.md](explanations/how-it-works.md)) — Pipeline overview, scoring math, and observability hooks.

Use `uv run mkdocs serve --dev-addr 127.0.0.1:4000` while editing to preview changes locally.
