---
applyTo: "**/*.py,pyproject.toml"
---

# Mandatory Validation Rules

These validation steps MUST run after ANY code change (addition, edit, or deletion) in this repository.

## When to Run

- **After every code change** (add, edit, delete)
- **On demand** when explicitly requested
- **Before marking any task complete**

## Validation Loop (MANDATORY)

Run these in order after EVERY code change:

> **Heads-up:** `uv run` executes commands inside the project-managed `.venv`, so Python tooling only sees the installed `article_extractor` package when invoked through `uv run` ([uv docs](https://docs.astral.sh/uv/concepts/projects/run/)).

### Phase 0: Environment Refresh

```bash
uv sync --locked --all-extras --dev
uv sync --upgrade --all-extras --dev
uv run playwright install
```

### Phase 1: Code Quality

```bash
# 1. Format and lint
uv run ruff format .
uv run ruff check --fix .

# 2. Check for type errors (use get_errors tool on changed files)
# Fix ALL errors before proceeding

# 3. Run the full unit test suite (single command, keep coverage ≥ 93%)
timeout 60 uv run pytest tests/ --cov=src/article_extractor --cov-report=term-missing
```

> Coverage expectation: if the reported total drops below **93%**, treat the run as failed and address gaps before proceeding.


### Phase 2: CLI Testing

```bash
# 4. Test CLI help
uv run article-extractor --help

# 5. Test with sample URL
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia
```

### Phase 3: Docs Build

```bash
# 6. Build docs in strict mode to catch nav/anchor drift early
uv run mkdocs build --strict

# 7. Rebuild docs after nav/theme changes to clear cached assets
uv run mkdocs build --strict --clean
```

### Phase 4: Server Testing

```bash
# 8. Test server startup (optional, manual verification)
uv run uvicorn article_extractor.server:app --port 3000 &
curl http://localhost:3000/health
```

### Phase 5: Docker Validation

```bash
# 9. Run the Python Docker harness (rebuilds image, resets storage, fires parallel smoke requests)
uv run scripts/debug_docker_deployment.py
```

## Quick Validation (Minimum Required)

For small changes, at minimum run:

```bash
uv run ruff format . && uv run ruff check --fix .
timeout 60 uv run pytest tests/ -v
uv run article-extractor --help
uv run mkdocs build --strict
```

## Anti-Patterns to Avoid

- ❌ Skipping validation after "small" changes
- ❌ Not testing with `article-extractor --help` after CLI changes
- ❌ Leaving failing tests
- ❌ Proceeding with type errors

## Definition of Done

A change is NOT complete until:

1. ✅ `uv run ruff format . && uv run ruff check --fix .` passes
2. ✅ No type errors in changed files
3. ✅ `timeout 60 uv run pytest tests/ -v` passes
4. ✅ `uv run article-extractor --help` works
5. ✅ Docker build succeeds (if Dockerfile changed)
