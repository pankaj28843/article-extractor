# Development Workflow

Follow these steps to set up a local environment and pass the validation loop before opening a PR.

## Setup

```bash
git clone https://github.com/pankaj28843/article-extractor.git
cd article-extractor
uv sync --all-extras
```

Use `uv sync --extra docs` if you only need MkDocs tooling.

## Validation Loop

Per [.github/instructions/validation.instructions.md](https://github.com/pankaj28843/article-extractor/blob/main/.github/instructions/validation.instructions.md):

1. `uv run ruff format .`
2. `uv run ruff check --fix .`
3. `PYTHONPATH=src uv run pytest tests/ --cov=src/article_extractor --cov-report=term-missing` (coverage must stay ≥93%).
4. `uv run article-extractor --help`
5. `uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia`
6. `uv run mkdocs build`
7. Run Docker smoke tests when touching container/server code: `uv run scripts/debug_docker_deployment.py`.

Always run the commands in order and fix failures immediately—green tests are non-negotiable.

## Coding Standards

- Honor the deep-module boundaries described in `.github/instructions/software-engineering-principles.instructions.md`.
- When documenting CLI/server behavior, cite authoritative sources (TechDocs, MkDocs, GitHub Pages docs) and paste real command output.
- Use `uv run` for all Python commands (Prime Directive).

## Docs Contributions

- Pair code changes with documentation updates in `docs/` so README can stay concise. Slot new material into the Tutorials / How-To / Reference / Explanation buckets already represented in the docs navigation.
