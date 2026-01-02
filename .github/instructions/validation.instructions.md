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

### Phase 1: Code Quality

```bash
# 1. Format and lint
uv run ruff format .
uv run ruff check --fix .

# 2. Check for type errors (use get_errors tool on changed files)
# Fix ALL errors before proceeding

# 3. Run tests
uv run pytest tests/ -v
```

### Phase 2: CLI Testing

```bash
# 4. Test CLI help
uv run article-extractor --help

# 5. Test with sample URL
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia
```

### Phase 3: Server Testing

```bash
# 6. Test server startup (optional, manual verification)
uv run uvicorn article_extractor.server:app --port 3000 &
curl http://localhost:3000/health
```

### Phase 4: Docker Validation

```bash
# 7. Run the Docker debug harness (rebuilds image, publishes random port, runs smoke curl)
./scripts/debug-docker-deployment.sh
```

## Quick Validation (Minimum Required)

For small changes, at minimum run:

```bash
uv run ruff format . && uv run ruff check --fix .
uv run pytest tests/ -v
uv run article-extractor --help
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
3. ✅ `uv run pytest tests/ -v` passes
4. ✅ `uv run article-extractor --help` works
5. ✅ Docker build succeeds (if Dockerfile changed)
