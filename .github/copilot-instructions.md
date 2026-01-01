# AI Coding Agent Instructions for article-extractor

**Project Context**: Pure-Python article extraction library and HTTP service. Extracts main content from HTML documents and converts to clean Markdown. Provides Python library, FastAPI HTTP server, and CLI tool. Uses JustHTML for parsing and Readability-style scoring for content detection.

## Core Philosophy

**NO BACKWARD COMPATIBILITY** - Active development project. Break things freely unless explicitly asked to maintain compatibility. Focus on making the code better, not preserving old patterns.
**MINIMAL CODE** - Ship the minimal implementation that satisfies the requirement. Avoid abstraction layers until repeated use proves necessity.
**RESILIENT BUT TRANSPARENT** - Harden workflows against expected failures, but let exceptions bubble—never mask errors with broad `try/except` blocks.
**GREEN TESTS ALWAYS** - All unit tests MUST pass after every change. If you encounter a failing test:
1. Fix it if testing valid behavior your changes broke
2. Update it if testing outdated behavior
3. Delete it if testing removed functionality
**NO SUMMARY REPORTS** - Do NOT create summary documents or write-ups unless explicitly requested.

## Prime Directives

- Use `uv run` before any Python command: `uv run pytest`, `uv run article-extractor`, etc.
- **Green-before-done**: Do not say "done" until edited Python files import cleanly and tests pass.
- **Tests are mandatory** for any change affecting code paths
- **Never hallucinate**: Do not invent files, paths, models, or settings. Search the repo first.
- **TechDocs-first research**: Check TechDocs before implementing (see workflow below)
- **Verify before documenting**: Run commands and paste actual output. Never invent expected output blocks.

## TechDocs Research Workflow

**Start every research session with this sequence**:
1. `mcp_techdocs_list_tenants()` → discover available documentation sources
2. `mcp_techdocs_describe_tenant(codename="...")` → understand tenant capabilities and test queries
3. `mcp_techdocs_root_search(tenant_codename="...", query="...")` → find relevant patterns
4. `mcp_techdocs_root_fetch(tenant_codename="...", uri="...")` → read full documentation

**Key tenants for this project**: `python`/`pytest` (Python best practices), `fastapi` (HTTP server), `docker` (containerization), `github-platform` (GitHub Actions/CI)
**Full TechDocs guide**: See `.github/instructions/techdocs.instructions.md`

## Validation & Testing

**All code changes require this validation loop**:
```bash
uv sync --extra dev
uv run ruff format . && uv run ruff check --fix .
uv run pytest tests/ -v
```

**Full validation checklist**: See `.github/instructions/validation.instructions.md`

## Testing Rules

- Unit tests for every new function/class
- Test behavior, not implementation
- Use `pytest-asyncio` for async tests
- Mark async tests with `@pytest.mark.asyncio`

**Pytest patterns**: `.github/instructions/tests.instructions.md`

## Planning

For non-trivial tasks, create a PRP plan at `.github/ai-agent-plans/{ISO-timestamp}-{slug}-plan.md`

**PRP template**: `.github/instructions/PRP-README.md`

## Code Quality

- Prefer small, incremental diffs over giant drops
- No verbose comments or placeholder TODOs
- Function complexity >15 → refactor; single function >120 LOC → refactor
- Minimize rename/reordering churn unless clarity win is clear

## Path-Specific Instructions

| Pattern | File | Purpose |
|---------|------|---------|
| `**/*.py`, `pyproject.toml` | [validation.instructions.md](instructions/validation.instructions.md) | Mandatory validation loop |
| `tests/**/*.py` | [tests.instructions.md](instructions/tests.instructions.md) | Pytest standards |
| GitHub CLI workflows | [gh-cli.instructions.md](instructions/gh-cli.instructions.md) | Non-interactive mode patterns |

## Prompt Library

Reusable templates in `.github/prompts/`:

- `prpPlanOnly.prompt.md` - Planning mode (no code changes until approved)
- `cleanCodeRefactor.prompt.md` - Rename/restructure without behavior changes
- `bugFixRapidResponse.prompt.md` - Quick surgical bug fixes
- `testHardening.prompt.md` - Improve test coverage/reliability
- `iterativeCodeSimplification.prompt.md` - Reduce LOC while maintaining behavior

## Project-Specific Context

### Key Files
```yaml
- file: src/article_extractor/extractor.py
  why: Core extraction logic with Readability-style scoring

- file: src/article_extractor/server.py
  why: FastAPI HTTP server

- file: src/article_extractor/cli.py
  why: CLI entry point

- file: pyproject.toml
  why: Project configuration, dependencies, entry points
```

### Validation Commands
```bash
# Format and lint
uv run ruff format . && uv run ruff check --fix .

# Run tests
uv run pytest tests/ -v

# Test CLI locally
uv run article-extractor --help
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia

# Test server locally
uv run uvicorn article_extractor.server:app --reload --port 3000

# Build and test Docker image
docker build -t article-extractor .
docker run --rm -p 3000:3000 article-extractor
```
