"""Tests for FastAPI server module."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from article_extractor.server import app
from article_extractor.types import ArticleResult


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_result():
    """Sample extraction result."""
    return ArticleResult(
        url="https://example.com/article",
        title="Test Article Title",
        content="<p>This is the article content.</p>",
        markdown="# Test Article Title\n\nThis is the article content.",
        excerpt="This is the article content.",
        word_count=5,
        success=True,
        author="Jane Doe",
    )


@pytest.fixture
def failed_result():
    """Failed extraction result."""
    return ArticleResult(
        url="https://example.com/article",
        title="",
        content="",
        markdown="",
        excerpt="",
        word_count=0,
        success=False,
        error="Failed to extract article",
    )


def test_root_endpoint(client):
    """Test root health check endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "article-extractor-server"
    assert data["status"] == "running"
    assert "version" in data


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["cache"]["max_size"] >= 1
    assert data["cache"]["size"] >= 0
    assert data["worker_pool"]["max_workers"] >= 1


def test_extract_article_success(client, mock_result):
    """Test successful article extraction."""
    with patch(
        "article_extractor.server.extract_article_from_url",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = client.post("/", json={"url": "https://example.com/article"})

    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://example.com/article"
    assert data["title"] == "Test Article Title"
    assert data["byline"] == "Jane Doe"
    assert data["content"] == "<p>This is the article content.</p>"
    assert data["markdown"] == "# Test Article Title\n\nThis is the article content."
    assert data["word_count"] == 5
    assert data["success"] is True
    assert data["dir"] == "ltr"


def test_extract_article_failure(client, failed_result):
    """Test failed article extraction."""
    with patch(
        "article_extractor.server.extract_article_from_url",
        new_callable=AsyncMock,
        return_value=failed_result,
    ):
        response = client.post("/", json={"url": "https://example.com/article"})

    assert response.status_code == 422
    data = response.json()
    assert "Failed to extract article" in data["detail"]


def test_extract_article_invalid_url(client):
    """Test extraction with invalid URL."""
    response = client.post("/", json={"url": "not-a-url"})
    assert response.status_code == 422


def test_extract_article_exception(client):
    """Test unexpected exception during extraction."""
    with patch(
        "article_extractor.server.extract_article_from_url",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Unexpected error"),
    ):
        response = client.post("/", json={"url": "https://example.com/article"})

    assert response.status_code == 500
    data = response.json()
    assert "Internal server error" in data["detail"]


def test_openapi_docs_available(client):
    """Test that OpenAPI docs are available."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_available(client):
    """Test that ReDoc is available."""
    response = client.get("/redoc")
    assert response.status_code == 200


def test_extraction_with_null_author(client):
    """Test extraction result with null author."""
    result = ArticleResult(
        url="https://example.com/article",
        title="Article Without Author",
        content="<p>Content</p>",
        markdown="Content",
        excerpt="Content",
        word_count=1,
        success=True,
        author=None,
    )

    with patch(
        "article_extractor.server.extract_article_from_url",
        new_callable=AsyncMock,
        return_value=result,
    ):
        response = client.post("/", json={"url": "https://example.com/article"})

    assert response.status_code == 200
    data = response.json()
    assert data["byline"] is None


def test_extraction_options_applied(client, mock_result):
    """Test that extraction options are passed correctly."""
    with patch(
        "article_extractor.server.extract_article_from_url",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_extract:
        client.post("/", json={"url": "https://example.com/article"})

    call_args = mock_extract.call_args
    options = call_args.kwargs["options"]
    assert options.min_word_count == 150
    assert options.min_char_threshold == 500
    assert options.include_images is True
    assert options.include_code_blocks is True
    assert options.safe_markdown is True
    assert call_args.kwargs["executor"] is not None


def test_extract_article_uses_cache(client, mock_result):
    """Repeated requests for the same URL should hit the in-memory cache."""
    with patch(
        "article_extractor.server.extract_article_from_url",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_extract:
        first = client.post("/", json={"url": "https://example.com/article"})
        second = client.post("/", json={"url": "https://example.com/article"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert mock_extract.call_count == 1


def test_cache_size_env_override(monkeypatch):
    """Cache size should respect ARTICLE_EXTRACTOR_CACHE_SIZE env overrides."""
    monkeypatch.setenv("ARTICLE_EXTRACTOR_CACHE_SIZE", "5")
    with TestClient(app) as local_client:
        data = local_client.get("/health").json()
    assert data["cache"]["max_size"] == 5
    monkeypatch.delenv("ARTICLE_EXTRACTOR_CACHE_SIZE", raising=False)
