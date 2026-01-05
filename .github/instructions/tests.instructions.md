---
applyTo:
  - "**/tests/**"
---

# Test Instructions (article-extractor)

## General Rules

- Use `@pytest.mark.asyncio` for all async test functions
- Test method names start with `test_` describing behavior (e.g., `test_extract_article_returns_title`)
- No docstrings in test classes/methods—clear method names suffice
- Avoid verbose comments; test code should be self-documenting
- Use fixtures over ad-hoc setup to reduce duplication
- Coverage check: `timeout 60 uv run pytest tests/ --cov=src/article_extractor --cov-report=term-missing`, minimum 90% overall and close to 100% for new code.
## Test Behavior, Not Implementation

```python
# GOOD: Tests what the function does
def test_extract_article_finds_main_content(sample_html):
    result = extract_article(sample_html)
    assert result.success
    assert result.word_count > 100

# BAD: Tests how it does it
def test_uses_justhtml_parser():
    mock_parser = Mock()
    extract_article(html, parser=mock_parser)
    mock_parser.parse.assert_called_once()  # Testing implementation
```

## Mock Only External Boundaries

```python
# GOOD: Mock external HTTP calls
with patch("article_extractor.fetcher.httpx.AsyncClient") as mock_client:
    mock_client.return_value.get.return_value = mock_response
    result = await extract_article_from_url(url)

# BAD: Mock internal methods
with patch.object(extractor, "_score_candidate"):
    # Fragile, breaks on refactoring
```

## Test Organization

```
tests/
├── test_extractor.py   # Extraction logic tests
├── test_scorer.py      # Scoring algorithm tests
├── test_server.py      # FastAPI endpoint tests
├── test_cli.py         # CLI interface tests
├── test_fetcher.py     # URL fetching tests
└── conftest.py         # Shared fixtures
```

## Validation Commands

```bash
# Run all tests
timeout 60 uv run pytest tests/ -v

# Run with coverage
timeout 60 uv run pytest tests/ --cov=src/article_extractor --cov-report=term-missing

# Run specific test file
timeout 60 uv run pytest tests/test_extractor.py -v

# Run tests matching pattern
timeout 60 uv run pytest tests/ -k "test_extract" -v
```

## Anti-Patterns

- **No fake tests** - Don't assert that constants equal literals
- **No mocking framework internals** - Only mock true external dependencies
- **No tests requiring network calls** in unit tests - Mock HTTP clients
- **No tests with side effects** - Each test should be independent
- **No leaked internal URLs** - Use `example.com`, `wiki.example.com` for test URLs; never commit real company domains, project codes, or internal page IDs

## URL Hygiene in Tests

When writing tests with URLs, always use generic placeholders:

```python
# GOOD: Generic example domains
url = "https://wiki.example.com/spaces/DOCS/pages/12345678/GettingStarted"
url = "https://example.com/blog/post-1"

# BAD: Leaked internal URLs
url = "https://confluence.company.net/spaces/PROJ/pages/123456/RealPage"  # ❌
```
