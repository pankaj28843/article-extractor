# Development Workflow Guide

This guide covers the complete development workflow for article-extractor.

**Audience**: Contributors updating code, docs, or release workflows.

**Prerequisites**: Python 3.12+, `uv`, and Docker if you need container validation.

**Time**: ~30 minutes for code changes, longer if you run Docker smoke checks.

**What you'll learn**: Local setup, validation loop, and release steps.

## Quick Start for Contributors

### 1. Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/pankaj28843/article-extractor.git
cd article-extractor

# Install uv if not available
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies
uv sync --all-extras --dev

# Install Playwright browsers (if using playwright extra)
uv run playwright install chromium
```

### 2. Install CLI as Editable Tool (Recommended for Active Development)

For rapid iteration where you want the `article-extractor` command to reflect your local changes immediately:

```bash
# Install as editable tool (changes to src/ are reflected immediately)
uv tool install --editable --force --refresh --reinstall ".[all]"

# Now you can run without `uv run` prefix:
article-extractor --help
article-extractor https://example.com
article-extractor crawl --seed https://example.com --output-dir ./output
```

This is especially useful when debugging extraction issues with real URLs. The `--force --refresh --reinstall` flags ensure a clean install that picks up all your local changes.

> **Note**: When done debugging, remember that any URL-specific test cases should use `example.com` or other generic domains—never leak real internal URLs into tests or documentation.

### 3. Before Making Changes

```bash
# Create a new branch
git checkout -b feature/your-feature-name

# Make sure tests pass
uv run pytest -v
```

### 4. Development Cycle

```bash
# Make your changes to code

# Format code (automatic fixes)
uv run ruff format .

# Lint code (automatic fixes where possible)
uv run ruff check --fix .

# Run tests with coverage
uv run pytest --cov=src/article_extractor --cov-report=term-missing -v

# Run specific test file
uv run pytest tests/test_extractor.py -v
```

### 5. Pre-Commit Checklist

Run the pre-commit check script:
```bash
./scripts/pre-commit-check.sh
```

Or manually:
```bash
# 1. Format code
uv run ruff format .

# 2. Lint code
uv run ruff check --fix .

# 3. Run all tests
uv run pytest --cov=src/article_extractor --cov-report=term-missing -v

# 4. Verify coverage is 94%+
uv run coverage report
```

### 6. Docker Smoke Validation

Run the automated Docker debug harness whenever you need to validate the container image and Playwright storage wiring end-to-end:

```bash
uv run scripts/debug_docker_deployment.py
```

The shell entrypoint now delegates to `scripts/debug_docker_deployment.py`, which:

- Rebuilds `article-extractor:local` (unless `--skip-build` is supplied)
- Deletes and recreates `tmp/docker-smoke-data/` via `article_extractor.storage`
- Runs the container with a random published port and shared storage mount
- Waits for `/health` and then POSTs ~20 curated URLs in parallel (configurable via `--urls-file`)
- Aggregates the HTTP status for every URL, printing excerpts for failures and retrying once per target by default (`--retries`)
- Verifies that `storage_state.json` exists, is non-empty, and contains both Playwright `origins` and `cookies`
- Streams the final log tail and prints a ready-to-run `curl` snippet before cleaning up

You can pass any harness flag through the wrapper, for example `uv run scripts/debug_docker_deployment.py --concurrency 8 --urls-file urls.txt`. The underlying Python script also exposes `--keep-container` if you want to inspect the running container manually.

### 7. Commit and Push

```bash
# Stage your changes
git add .

# Commit with descriptive message
git commit -m "feat: add new feature description"

# Push to your branch
git push origin feature/your-feature-name

# Create pull request on GitHub
```

## CI/CD Pipeline

All pull requests and commits to `main` trigger automated checks:

### CI Workflow (`.github/workflows/ci.yml`)

**Test Job:**
- Runs on Python 3.12, 3.13, 3.14 (Ubuntu latest)
- Executes full test suite with coverage reporting
- Enforces a ≥90% coverage threshold directly via pytest
- Uploads coverage to Codecov (Python 3.12 only)

**Lint Job:**
- Checks code formatting with Ruff
- Lints code with Ruff
- Optional: Type checking with mypy

**Build Job:**
- Builds Python package
- Verifies package can be imported
- Uploads build artifacts

### Other Workflows

- **CodeQL** (`.github/workflows/codeql.yml`): Security scanning
- **Docker** (`.github/workflows/docker.yml`): Container builds
- **Publish** (`.github/workflows/publish.yml`): PyPI publishing
- **Security** (`.github/workflows/security.yml`): Dependency scanning

## GitHub Copilot Integration

The repository includes comprehensive Copilot instructions to help you code faster:

### Repository-Wide Instructions
- `.github/copilot-instructions.md` - Complete project guide

### Path-Specific Instructions
- `.github/instructions/validation.instructions.md` - For `**/*.py`
- `.github/instructions/tests.instructions.md` - For `tests/**/*.py`
- `.github/instructions/gh-cli.instructions.md` - For GitHub CLI usage

### Prompt Files
Located in `.github/prompts/`:
- `prpPlanOnly.prompt.md` - Planning mode (creates plan without code changes)
- `cleanCodeRefactor.prompt.md` - Rename/restructure without behavior changes
- `bugFixRapidResponse.prompt.md` - Quick surgical bug fixes
- `testHardening.prompt.md` - Improve test coverage and reliability
- `iterativeCodeSimplification.prompt.md` - Reduce LOC while maintaining behavior

### Using Prompt Files in VS Code

1. Open Copilot Chat
2. Click "Attach context" icon
3. Select "Prompt..." and choose a prompt file
4. Add any additional context
5. Submit the prompt

## Code Style Guidelines

### Python Code

- **Type Hints**: Required on all function signatures
- **Imports**: `from __future__ import annotations` at top
- **Docstrings**: Required for all public APIs
- **Formatting**: Handled by Ruff (runs automatically)
- **Linting**: Enforced by Ruff

### Architecture Patterns

**Instance-Level State (CRITICAL):**
```python
# ❌ WRONG - Module-level mutable state
_cache = {}

# ✅ CORRECT - Instance-level state
class Processor:
    __slots__ = ("_cache",)
    def __init__(self):
        self._cache = {}
```

**Async Patterns:**
```python
# Context managers
async with PlaywrightFetcher() as fetcher:
    html, status = await fetcher.fetch(url)

# Return tuples
async def fetch(url: str) -> tuple[str, int]:
    return html, status_code
```

**Error Handling:**
```python
# Return structured results, don't raise
try:
    result = process()
    return ArticleResult(success=True, ...)
except Exception as e:
    return ArticleResult(success=False, error=str(e), ...)
```

## Testing Guidelines

### Test Organization

```python
@pytest.mark.unit
class TestFeature:
    def test_success_case(self, fixture):
        result = function_under_test()
        assert result.success is True
    
    def test_failure_case(self):
        result = function_with_bad_input()
        assert result.success is False
```

### Coverage Requirements

- **Overall**: 94%+ (enforced in CI)
- **New Code**: 100%
- **Critical Paths**: 100%

### Running Tests

```bash
# All tests
uv run pytest -v

# Specific file
uv run pytest tests/test_extractor.py -v

# With coverage
uv run pytest --cov=src/article_extractor --cov-report=term-missing

# Generate HTML coverage report
uv run pytest --cov=src/article_extractor --cov-report=html
open htmlcov/index.html
```

## Common Development Tasks

### Adding a New Feature

1. **Plan**: Review existing code for similar patterns
2. **Test First**: Write tests for new functionality
3. **Implement**: Write code with type hints and docstrings
4. **Test**: Ensure 100% coverage for new code
5. **Document**: Update README if user-facing
6. **Lint**: Run `uv run ruff format . && uv run ruff check --fix .`
7. **Verify**: Run full test suite

### Fixing a Bug

1. **Reproduce**: Write a failing test
2. **Fix**: Implement the fix
3. **Verify**: Ensure test passes
4. **Regression**: Run full test suite
5. **Document**: Add to CHANGELOG if significant

### Refactoring

1. **Baseline**: Run tests to establish passing state
2. **Small Steps**: Make incremental changes
3. **Test After Each**: Ensure tests still pass
4. **Coverage**: Maintain or improve coverage
5. **Lint**: Ensure code style maintained

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create git tag: `git tag v0.2.0`
4. Push tag: `git push origin v0.2.0`
5. GitHub Actions will build and publish to PyPI

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/pankaj28843/article-extractor/issues)
- **Discussions**: [GitHub Discussions](https://github.com/pankaj28843/article-extractor/discussions)
- **Copilot**: Ask in Copilot Chat with repository context

## Useful Commands Reference

```bash
# Development
uv sync --all-extras --dev          # Install all dependencies
uv run article-extractor <url>      # Run CLI
uv run article-extractor --server   # Run server

# Testing
uv run pytest -v                    # Run all tests
uv run pytest -k test_name          # Run specific test
uv run pytest --cov                 # Run with coverage
uv run pytest -m unit               # Run unit tests only

# Code Quality
uv run ruff format .                # Format code
uv run ruff check --fix .           # Lint and fix
./scripts/pre-commit-check.sh       # Pre-commit checks

# Building
uv build                            # Build package
docker build -t article-extractor . # Build Docker image
```

## File Structure Reference

```
article-extractor/
├── .github/
│   ├── copilot-instructions.md       # Main Copilot instructions
│   ├── instructions/                 # Path-specific instructions
│   │   ├── PRP-README.md             # Planning template guide
│   │   ├── gh-cli.instructions.md    # GitHub CLI usage
│   │   ├── techdocs.instructions.md  # TechDocs research workflow
│   │   ├── tests.instructions.md     # Testing guidelines
│   │   └── validation.instructions.md # Validation checklist
│   ├── prompts/                      # Reusable prompt files
│   │   ├── prpPlanOnly.prompt.md     # Planning mode
│   │   ├── cleanCodeRefactor.prompt.md
│   │   ├── bugFixRapidResponse.prompt.md
│   │   ├── testHardening.prompt.md
│   │   └── iterativeCodeSimplification.prompt.md
│   └── workflows/                    # GitHub Actions
│       ├── ci.yml                    # Main CI/CD
│       ├── codeql.yml                # Security scanning
│       ├── docker.yml                # Container builds
│       ├── publish.yml               # PyPI publishing
│       └── security.yml              # Dependency scanning
├── src/article_extractor/            # Source code
├── tests/                            # Test files
└── scripts/                          # Helper scripts
    └── pre-commit-check.sh           # Pre-commit validation
```
