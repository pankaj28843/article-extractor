"""Tests for FastAPI server module."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from article_extractor.server import (
    ExtractionRequest,
    ExtractionResponse,
    ExtractionResponseCache,
    NetworkRequest,
    _build_cache_key,
    _determine_threadpool_size,
    _lookup_cache,
    _read_cache_size,
    _resolve_preference,
    _resolve_request_network_options,
    _store_cache_entry,
    app,
    configure_network_defaults,
    general_exception_handler,
    http_exception_handler,
    set_prefer_playwright,
)
from article_extractor.types import ArticleResult, ExtractionOptions, NetworkOptions


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
    sentinel_network = NetworkOptions(user_agent="sentinel")
    with (
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract,
        patch(
            "article_extractor.server.resolve_network_options",
            return_value=sentinel_network,
        ),
    ):
        response = client.post("/", json={"url": "https://example.com/article"})

    assert response.status_code == 200
    mock_extract.assert_awaited_once()
    kwargs = mock_extract.await_args.kwargs
    assert kwargs["network"] is sentinel_network
    assert kwargs["prefer_playwright"] is True
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
    with (
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=failed_result,
        ),
        patch("article_extractor.server.resolve_network_options"),
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
    with (
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Unexpected error"),
        ),
        patch("article_extractor.server.resolve_network_options"),
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

    with (
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=result,
        ),
        patch("article_extractor.server.resolve_network_options"),
    ):
        response = client.post("/", json={"url": "https://example.com/article"})

    assert response.status_code == 200
    data = response.json()
    assert data["byline"] is None


def test_extraction_options_applied(client, mock_result):
    """Test that extraction options are passed correctly."""
    with (
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract,
        patch("article_extractor.server.resolve_network_options") as mock_network,
    ):
        mock_network.return_value = NetworkOptions()
        client.post("/", json={"url": "https://example.com/article"})

    call_args = mock_extract.call_args
    options = call_args.kwargs["options"]
    assert options.min_word_count == 150
    assert options.min_char_threshold == 500
    assert options.include_images is True
    assert options.include_code_blocks is True
    assert options.safe_markdown is True
    assert call_args.kwargs["executor"] is not None
    assert call_args.kwargs["network"] is mock_network.return_value


def test_extract_article_uses_cache(client, mock_result):
    """Repeated requests for the same URL should hit the in-memory cache."""
    with (
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract,
        patch("article_extractor.server.resolve_network_options"),
    ):
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


def test_threadpool_env_override(monkeypatch):
    """Threadpool size should use ARTICLE_EXTRACTOR_THREADPOOL_SIZE overrides."""

    monkeypatch.setenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", "3")
    with TestClient(app) as local_client:
        data = local_client.get("/health").json()
    assert data["worker_pool"]["max_workers"] == 3
    monkeypatch.delenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", raising=False)


def test_network_payload_overrides(client, mock_result, tmp_path):
    """Network payload should flow into resolve_network_options overrides."""

    storage_path = tmp_path / "state.json"
    sent_payload = {
        "user_agent": "Custom-UA",
        "random_user_agent": True,
        "proxy": "http://proxy:8080",
        "proxy_bypass": ["internal.local"],
        "headed": True,
        "user_interaction_timeout": 5,
        "storage_state": str(storage_path),
    }

    with (
        patch("article_extractor.server.resolve_network_options") as mock_network,
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        client.post(
            "/",
            json={
                "url": "https://example.com/article",
                "network": sent_payload,
                "prefer_playwright": False,
            },
        )

    kwargs = mock_network.call_args.kwargs
    assert kwargs["user_agent"] == "Custom-UA"
    assert kwargs["randomize_user_agent"] is True
    assert kwargs["proxy"] == "http://proxy:8080"
    assert kwargs["proxy_bypass"] == ["internal.local"]
    assert kwargs["headed"] is True
    assert kwargs["user_interaction_timeout"] == 5
    assert kwargs["storage_state_path"] == str(storage_path)


def test_prefer_playwright_override(client, mock_result):
    """Request-level preference should override server default."""

    with (
        patch("article_extractor.server.resolve_network_options"),
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract,
    ):
        client.post(
            "/",
            json={"url": "https://example.com/article", "prefer_playwright": False},
        )

    assert mock_extract.await_args.kwargs["prefer_playwright"] is False


def test_configure_helpers_store_state():
    """configure_network_defaults and set_prefer_playwright should set app state."""

    original_network = getattr(app.state, "network_defaults", None)
    original_prefer = getattr(app.state, "prefer_playwright", True)
    network = NetworkOptions(user_agent="helper")
    configure_network_defaults(network)
    set_prefer_playwright(False)
    assert app.state.network_defaults is network
    assert app.state.prefer_playwright is False
    app.state.network_defaults = original_network
    app.state.prefer_playwright = original_prefer


def test_read_cache_size_invalid_env(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_CACHE_SIZE", "not-a-number")

    caplog.set_level("WARNING")
    size = _read_cache_size()

    assert size == 1000
    assert any("Invalid ARTICLE_EXTRACTOR_CACHE_SIZE" in msg for msg in caplog.messages)
    monkeypatch.delenv("ARTICLE_EXTRACTOR_CACHE_SIZE", raising=False)


def test_determine_threadpool_size_invalid_requests(monkeypatch):
    monkeypatch.delenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", raising=False)
    default_value = _determine_threadpool_size()

    monkeypatch.setenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", "0")
    assert _determine_threadpool_size() == default_value

    monkeypatch.setenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", "abc")
    assert _determine_threadpool_size() == default_value

    monkeypatch.delenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", raising=False)


def test_build_cache_key_reflects_options():
    options = ExtractionOptions(
        min_word_count=10,
        min_char_threshold=20,
        include_images=False,
        include_code_blocks=False,
        safe_markdown=False,
    )

    key = _build_cache_key("https://example.com", options)

    assert key == "https://example.com|10|20|0|0|0"


@pytest.mark.asyncio
async def test_cache_helpers_roundtrip():
    cache = ExtractionResponseCache(2)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(cache=cache, cache_lock=asyncio.Lock())
        )
    )
    response = ExtractionResponse(
        url="https://example.com",
        title="Cached",
        byline=None,
        dir="ltr",
        content="<p>cached</p>",
        length=12,
        excerpt="cached",
        siteName=None,
        markdown="cached",
        word_count=2,
        success=True,
    )

    await _store_cache_entry(request, "key", response)
    cached = await _lookup_cache(request, "key")

    assert cached == response


@pytest.mark.asyncio
async def test_lookup_cache_without_state_returns_none():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    assert await _lookup_cache(request, "missing") is None


def test_resolve_preference_prefers_request_override():
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(prefer_playwright=True))
    )
    extraction_request = ExtractionRequest(
        url="https://example.com",
        prefer_playwright=False,
    )

    assert _resolve_preference(extraction_request, request) is False


def test_resolve_preference_defaults_to_true_when_state_unspecified():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    extraction_request = ExtractionRequest(url="https://example.com")

    assert _resolve_preference(extraction_request, request) is True


def test_resolve_preference_uses_app_state_when_request_unspecified():
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(prefer_playwright=False))
    )
    extraction_request = ExtractionRequest(url="https://example.org")

    assert _resolve_preference(extraction_request, request) is False


def test_resolve_request_network_options_merges_payload(tmp_path):
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(network_defaults=NetworkOptions(proxy="http://base"))
        )
    )
    payload = NetworkRequest(
        user_agent="client",
        random_user_agent=True,
        proxy="http://client",
        proxy_bypass=["internal.local"],
        headed=True,
        user_interaction_timeout=4.5,
        storage_state=str(tmp_path / "client.json"),
    )
    extraction_request = ExtractionRequest(
        url="https://example.com",
        network=payload,
    )

    resolved = _resolve_request_network_options(extraction_request, request)

    assert resolved.user_agent == "client"
    assert resolved.proxy == "http://client"
    assert "internal.local" in resolved.proxy_bypass
    assert resolved.headed is True
    assert resolved.user_interaction_timeout == 4.5
    assert str(resolved.storage_state_path).endswith("client.json")


@pytest.mark.asyncio
async def test_http_exception_handler_formats_response():
    request = SimpleNamespace(url="http://testserver/resource")
    exc = HTTPException(status_code=418, detail="teapot")

    response = await http_exception_handler(request, exc)

    assert response.status_code == 418
    assert (
        response.body.decode()
        == '{"detail":"teapot","url":"http://testserver/resource"}'
    )


@pytest.mark.asyncio
async def test_general_exception_handler_returns_500():
    response = await general_exception_handler(SimpleNamespace(), RuntimeError("boom"))

    assert response.status_code == 500
    assert "Internal server error" in response.body.decode()
