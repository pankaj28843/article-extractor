"""Tests for FastAPI server module."""

# ruff: noqa: S108  # /tmp usage in tests is expected

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import article_extractor.server as server_module
from article_extractor.server import (
    ExtractionRequest,
    ExtractionResponse,
    ExtractionResponseCache,
    NetworkRequest,
    _build_cache_key,
    _determine_threadpool_size,
    _initialize_state_from_env,
    _lookup_cache,
    _read_cache_size,
    _read_prefer_playwright_env,
    _resolve_preference,
    _resolve_request_network_options,
    _store_cache_entry,
    app,
    configure_network_defaults,
    general_exception_handler,
    http_exception_handler,
    set_prefer_playwright,
)
from article_extractor.settings import reload_settings
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


def test_server_setup_logging_uses_settings():
    """Server should configure logging using ServiceSettings-derived values."""

    settings = SimpleNamespace(
        log_level="DEBUG",
        log_format="text",
        cache_size=256,
        log_diagnostics=True,
        prefer_playwright=False,
        build_network_env=lambda: {},
        determine_threadpool_size=lambda: 8,
    )

    with patch("article_extractor.server.setup_logging") as mock_setup:
        server_module._configure_logging(settings)

    mock_setup.assert_called_once_with(
        component="server",
        level="DEBUG",
        default_level="INFO",
        log_format="text",
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
    assert response.headers.get("X-Request-ID")
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


def test_request_id_header_preserved(client, mock_result):
    """Server should echo incoming X-Request-ID headers."""

    with (
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("article_extractor.server.resolve_network_options"),
    ):
        response = client.post(
            "/",
            json={"url": "https://example.com/article"},
            headers={"X-Request-ID": "abc123"},
        )

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "abc123"


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
    assert response.headers.get("X-Request-ID") == data["request_id"]


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
    assert response.headers.get("X-Request-ID") == data["request_id"]


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


def _sample_response(title: str) -> ExtractionResponse:
    return ExtractionResponse(
        url=f"https://example.com/{title}",
        title=title,
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


def test_cache_evicts_oldest_entry():
    cache = ExtractionResponseCache(1)
    cache.set("first", _sample_response("first"))
    cache.set("second", _sample_response("second"))

    assert cache.get("first") is None
    assert cache.get("second").title == "second"


def test_cache_size_env_override(monkeypatch):
    """Cache size should respect ARTICLE_EXTRACTOR_CACHE_SIZE env overrides."""
    monkeypatch.setenv("ARTICLE_EXTRACTOR_CACHE_SIZE", "5")
    reload_settings()
    with TestClient(app) as local_client:
        data = local_client.get("/health").json()
    assert data["cache"]["max_size"] == 5
    monkeypatch.delenv("ARTICLE_EXTRACTOR_CACHE_SIZE", raising=False)
    reload_settings()


def test_threadpool_env_override(monkeypatch):
    """Threadpool size should use ARTICLE_EXTRACTOR_THREADPOOL_SIZE overrides."""

    monkeypatch.setenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", "3")
    reload_settings()
    with TestClient(app) as local_client:
        data = local_client.get("/health").json()
    assert data["worker_pool"]["max_workers"] == 3
    monkeypatch.delenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", raising=False)
    reload_settings()


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


def test_network_payload_defaults_disable_storage(client, mock_result):
    """Server should leave storage_state unset when payload omits it."""

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
            },
        )

    kwargs = mock_network.call_args.kwargs
    assert kwargs["storage_state_path"] is None


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


def test_request_metrics_emitted(mock_result):
    emitter = MagicMock()
    emitter.enabled = True

    with (
        patch("article_extractor.server.build_metrics_emitter", return_value=emitter),
        patch("article_extractor.server.resolve_network_options"),
        patch(
            "article_extractor.server.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
    ):
        with TestClient(app) as local_client:
            response = local_client.post("/", json={"url": "https://example.com"})

    assert response.status_code == 200
    increment_call = emitter.increment.call_args
    assert increment_call.args[0] == "server_http_requests_total"
    assert increment_call.kwargs["tags"] == {
        "method": "POST",
        "status": "200",
        "path": "/",
        "status_group": "2xx",
    }


@pytest.mark.asyncio
async def test_request_context_logging_exception_path_emits_metrics():
    class StubURL:
        def __str__(self) -> str:  # pragma: no cover - helper
            return "https://example.com/fail"

        @property
        def path(self) -> str:
            return "/fail"

    emitter = MagicMock()
    emitter.enabled = True
    request = SimpleNamespace(
        headers={"x-request-id": "req-123"},
        state=SimpleNamespace(),
        method="GET",
        url=StubURL(),
        app=SimpleNamespace(state=SimpleNamespace(metrics_emitter=emitter)),
    )

    async def failing_call_next(_):
        raise RuntimeError("boom")

    with (
        patch("article_extractor.server.logger") as mock_logger,
        patch("article_extractor.server._emit_request_metrics") as mock_emit,
        pytest.raises(RuntimeError),
    ):
        await server_module.request_context_logging(request, failing_call_next)

    mock_logger.exception.assert_called_once()
    mock_emit.assert_called_once()


def test_configure_helpers_store_state(monkeypatch, tmp_path):
    """configure_network_defaults should merge env overrides before storing."""

    original_network = getattr(app.state, "network_defaults", None)
    original_prefer = getattr(app.state, "prefer_playwright", True)
    env_storage = tmp_path / "env.json"
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", str(env_storage))
    reload_settings()

    network = NetworkOptions(user_agent="helper")
    configure_network_defaults(network)
    set_prefer_playwright(False)

    stored = app.state.network_defaults
    assert stored is not network
    assert stored.user_agent == "helper"
    assert stored.storage_state_path == env_storage
    assert app.state.prefer_playwright is False

    app.state.network_defaults = original_network
    app.state.prefer_playwright = original_prefer
    monkeypatch.delenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", raising=False)
    reload_settings()


def test_read_prefer_playwright_env_parses_boolean(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", "0")
    reload_settings()

    assert _read_prefer_playwright_env() is False

    monkeypatch.setenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", "On")
    reload_settings()

    assert _read_prefer_playwright_env() is True

    monkeypatch.delenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", raising=False)
    reload_settings()


def test_read_prefer_playwright_env_warns_on_invalid(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", "maybe")
    caplog.set_level("WARNING")
    reload_settings()

    assert _read_prefer_playwright_env() is True
    assert any(
        "Invalid ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT" in message
        for message in caplog.messages
    )

    monkeypatch.delenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", raising=False)
    reload_settings()


def test_initialize_state_from_env_seeds_defaults(monkeypatch, tmp_path):
    alias_file = tmp_path / "state.json"
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", str(alias_file))
    monkeypatch.setenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", "false")
    reload_settings()

    state = SimpleNamespace()

    _initialize_state_from_env(state)

    assert state.prefer_playwright is False
    assert state.network_defaults.storage_state_path == Path(alias_file)

    monkeypatch.delenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", raising=False)
    monkeypatch.delenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", raising=False)
    reload_settings()


def test_initialize_state_from_env_respects_existing_values(monkeypatch):
    state = SimpleNamespace(
        network_defaults=NetworkOptions(proxy="http://base"),
        prefer_playwright=False,
    )

    monkeypatch.setenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", "true")
    reload_settings()

    _initialize_state_from_env(state)

    assert state.network_defaults.proxy == "http://base"
    assert state.prefer_playwright is False

    monkeypatch.delenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", raising=False)


def test_env_storage_state_flows_into_requests(monkeypatch, tmp_path, mock_result):
    alias_file = tmp_path / "env-state.json"
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", str(alias_file))
    reload_settings()
    original_network = getattr(app.state, "network_defaults", None)
    try:
        app.state.network_defaults = None

        with (
            TestClient(app) as local_client,
            patch(
                "article_extractor.server.extract_article_from_url",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_extract,
        ):
            response = local_client.post(
                "/",
                json={"url": "https://example.com/article"},
            )

        assert response.status_code == 200
        network = mock_extract.await_args.kwargs["network"]
        assert network.storage_state_path == alias_file
    finally:
        app.state.network_defaults = original_network
        monkeypatch.delenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", raising=False)
        reload_settings()


def test_read_cache_size_invalid_env(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_CACHE_SIZE", "not-a-number")

    caplog.set_level("WARNING")
    reload_settings()
    size = _read_cache_size()

    assert size == 1000
    assert any("Invalid ARTICLE_EXTRACTOR_CACHE_SIZE" in msg for msg in caplog.messages)
    monkeypatch.delenv("ARTICLE_EXTRACTOR_CACHE_SIZE", raising=False)
    reload_settings()


def test_determine_threadpool_size_invalid_requests(monkeypatch):
    monkeypatch.delenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", raising=False)
    default_value = _determine_threadpool_size()

    monkeypatch.setenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", "0")
    reload_settings()
    assert _determine_threadpool_size() == default_value

    monkeypatch.setenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", "abc")
    reload_settings()
    assert _determine_threadpool_size() == default_value

    monkeypatch.delenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", raising=False)
    reload_settings()


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


@pytest.mark.asyncio
async def test_store_cache_entry_without_lock_is_noop():
    cache = MagicMock(spec=ExtractionResponseCache)
    state = SimpleNamespace(cache=cache, cache_lock=None)
    request = SimpleNamespace(app=SimpleNamespace(state=state))

    await _store_cache_entry(request, "sample", _sample_response("noop"))

    cache.set.assert_not_called()


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
        network=payload.model_dump(),
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


@pytest.mark.asyncio
async def test_general_exception_handler_includes_request_id():
    request = SimpleNamespace(state=SimpleNamespace(request_id="abc123"))

    response = await general_exception_handler(request, RuntimeError("boom"))

    body = json.loads(response.body.decode())
    assert body["request_id"] == "abc123"
    assert response.headers["X-Request-ID"] == "abc123"


# --- Crawl API Tests ---


class TestCrawlJobStore:
    @pytest.mark.asyncio
    async def test_create_job_assigns_id(self):
        from article_extractor.server import CrawlJobStore
        from article_extractor.types import CrawlConfig

        store = CrawlJobStore()
        config = CrawlConfig(output_dir=Path("/tmp"), seeds=["https://example.com"])
        job = await store.create_job(config)

        assert job.job_id is not None
        assert job.status == "queued"
        assert job.config == config

    @pytest.mark.asyncio
    async def test_get_job_returns_created_job(self):
        from article_extractor.server import CrawlJobStore
        from article_extractor.types import CrawlConfig

        store = CrawlJobStore()
        config = CrawlConfig(output_dir=Path("/tmp"), seeds=["https://example.com"])
        created = await store.create_job(config)

        fetched = await store.get_job(created.job_id)

        assert fetched is not None
        assert fetched.job_id == created.job_id

    @pytest.mark.asyncio
    async def test_get_job_returns_none_for_missing(self):
        from article_extractor.server import CrawlJobStore

        store = CrawlJobStore()

        assert await store.get_job("nonexistent") is None

    @pytest.mark.asyncio
    async def test_update_job_updates_fields(self):
        from article_extractor.server import CrawlJobStore
        from article_extractor.types import CrawlConfig

        store = CrawlJobStore()
        config = CrawlConfig(output_dir=Path("/tmp"), seeds=["https://example.com"])
        job = await store.create_job(config)

        await store.update_job(job.job_id, status="running", progress=5, total=10)

        updated = await store.get_job(job.job_id)
        assert updated.status == "running"
        assert updated.progress == 5
        assert updated.total == 10

    @pytest.mark.asyncio
    async def test_can_start_respects_limit(self):
        from article_extractor.server import CrawlJobStore
        from article_extractor.types import CrawlConfig

        store = CrawlJobStore(max_concurrent=1)
        config = CrawlConfig(output_dir=Path("/tmp"), seeds=["https://example.com"])

        # Initially can start
        assert await store.can_start() is True

        # Create and mark running
        job = await store.create_job(config)
        await store.update_job(job.job_id, status="running")

        # Now cannot start
        assert await store.can_start() is False

    @pytest.mark.asyncio
    async def test_store_and_get_manifest(self):
        from article_extractor.server import CrawlJobStore
        from article_extractor.types import CrawlConfig, CrawlManifest

        store = CrawlJobStore()
        config = CrawlConfig(output_dir=Path("/tmp"), seeds=["https://example.com"])
        job = await store.create_job(config)

        manifest = CrawlManifest(
            job_id=job.job_id,
            started_at="2026-01-05T00:00:00Z",
            completed_at="2026-01-05T00:01:00Z",
            config=config,
            total_pages=5,
            successful=4,
            failed=1,
        )
        await store.store_manifest(job.job_id, manifest)

        fetched = await store.get_manifest(job.job_id)
        assert fetched is not None
        assert fetched.total_pages == 5


class TestCrawlEndpoints:
    def test_submit_crawl_requires_seeds_or_sitemaps(self, client):
        response = client.post(
            "/crawl",
            json={"output_dir": "/tmp/crawl-test"},
        )

        assert response.status_code == 400
        assert "seed URL or sitemap" in response.json()["detail"]

    def test_submit_crawl_validates_output_dir(self, client):
        response = client.post(
            "/crawl",
            json={
                "output_dir": "/nonexistent/path/that/cannot/be/created/deeply/nested",
                "seeds": ["https://example.com"],
            },
        )

        assert response.status_code == 400
        assert "output_dir" in response.json()["detail"]

    def test_submit_crawl_returns_job_id(self, client, tmp_path):
        with patch(
            "article_extractor.crawler.run_crawl", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = MagicMock(
                total_pages=1, successful=1, failed=0, skipped=0, duration_seconds=1.0
            )

            response = client.post(
                "/crawl",
                json={
                    "output_dir": str(tmp_path),
                    "seeds": ["https://example.com"],
                },
            )

            assert response.status_code == 202
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "queued"

    def test_get_job_status_returns_404_for_missing(self, client):
        response = client.get("/crawl/nonexistent-job-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_get_manifest_returns_404_for_missing_job(self, client):
        response = client.get("/crawl/nonexistent-job-id/manifest")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestCrawlRequestValidation:
    def test_crawl_request_defaults(self):
        from article_extractor.server import CrawlRequest

        request = CrawlRequest(
            output_dir="/tmp/crawl",
            seeds=["https://example.com"],
        )

        assert request.max_pages == 100
        assert request.max_depth == 3
        assert request.concurrency == 5
        assert request.rate_limit_delay == 1.0
        assert request.follow_links is True

    def test_crawl_request_custom_values(self):
        from article_extractor.server import CrawlRequest

        request = CrawlRequest(
            output_dir="/tmp/crawl",
            seeds=["https://example.com"],
            max_pages=50,
            max_depth=5,
            concurrency=10,
            rate_limit_delay=2.0,
            follow_links=False,
            allow_prefixes=["https://example.com/blog"],
            deny_prefixes=["https://example.com/admin"],
        )

        assert request.max_pages == 50
        assert request.max_depth == 5
        assert request.concurrency == 10
        assert request.rate_limit_delay == 2.0
        assert request.follow_links is False
        assert request.allow_prefixes == ["https://example.com/blog"]
        assert request.deny_prefixes == ["https://example.com/admin"]

    def test_crawl_job_response_model(self):
        from article_extractor.server import CrawlJobResponse

        response = CrawlJobResponse(
            job_id="test-123",
            status="running",
            progress=10,
            total=100,
            successful=8,
            failed=2,
            skipped=0,
        )

        assert response.job_id == "test-123"
        assert response.status == "running"
        assert response.progress == 10
        assert response.successful == 8


class TestCrawlJobRunner:
    @pytest.mark.asyncio
    async def test_run_crawl_job_records_metrics_and_manifest(
        self, monkeypatch, tmp_path
    ):
        from article_extractor.crawler import CrawlProgress
        from article_extractor.server import CrawlJobStore, _run_crawl_job
        from article_extractor.types import CrawlConfig, CrawlManifest, NetworkOptions

        class _Metrics:
            def __init__(self):
                self.enabled = True
                self.increments = []
                self.observations = []

            def increment(self, name, tags=None):
                self.increments.append((name, tags))

            def observe(self, name, value=None, tags=None):
                self.observations.append((name, value, tags))

        async def _fake_run_crawl(config, network=None, on_progress=None):
            assert network is not None
            if on_progress:
                on_progress(
                    CrawlProgress(
                        url="https://example.com/a",
                        status="success",
                        fetched=1,
                        successful=1,
                        failed=0,
                        skipped=0,
                        remaining=1,
                    )
                )
                on_progress(
                    CrawlProgress(
                        url="https://example.com/b",
                        status="failed",
                        fetched=2,
                        successful=1,
                        failed=1,
                        skipped=0,
                        remaining=0,
                    )
                )
                on_progress(
                    CrawlProgress(
                        url="https://example.com/c",
                        status="skipped",
                        fetched=2,
                        successful=1,
                        failed=1,
                        skipped=1,
                        remaining=0,
                    )
                )
            return CrawlManifest(
                job_id="job-1",
                started_at="start",
                completed_at="end",
                config=config,
                total_pages=2,
                successful=1,
                failed=1,
                skipped=1,
                duration_seconds=1.5,
            )

        monkeypatch.setattr("article_extractor.crawler.run_crawl", _fake_run_crawl)

        job_store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com/"])
        job = await job_store.create_job(config)
        metrics = _Metrics()

        await _run_crawl_job(
            job.job_id,
            config,
            NetworkOptions(),
            job_store,
            metrics,
        )

        updated = await job_store.get_job(job.job_id)
        assert updated.status == "completed"
        manifest = await job_store.get_manifest(job.job_id)
        assert manifest is not None
        assert metrics.observations
        assert any(
            (tags or {}).get("status") == "failed" for _, tags in metrics.increments
        )

    @pytest.mark.asyncio
    async def test_run_crawl_job_skips_metrics_when_disabled(
        self, monkeypatch, tmp_path
    ):
        from article_extractor.crawler import CrawlProgress
        from article_extractor.server import CrawlJobStore, _run_crawl_job
        from article_extractor.types import CrawlConfig, CrawlManifest, NetworkOptions

        class _Metrics:
            def __init__(self):
                self.enabled = False
                self.increments = []
                self.observations = []

            def increment(self, name, tags=None):
                self.increments.append((name, tags))

            def observe(self, name, value=None, tags=None):
                self.observations.append((name, value, tags))

        async def _fake_run_crawl(config, network=None, on_progress=None):
            if on_progress:
                on_progress(
                    CrawlProgress(
                        url="https://example.com/a",
                        status="success",
                        fetched=1,
                        successful=1,
                        failed=0,
                        skipped=0,
                        remaining=0,
                    )
                )
            return CrawlManifest(
                job_id="job-1",
                started_at="start",
                completed_at="end",
                config=config,
                total_pages=1,
                successful=1,
                failed=0,
                skipped=0,
                duration_seconds=1.5,
            )

        monkeypatch.setattr("article_extractor.crawler.run_crawl", _fake_run_crawl)

        job_store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com/"])
        job = await job_store.create_job(config)
        metrics = _Metrics()

        await _run_crawl_job(
            job.job_id,
            config,
            NetworkOptions(),
            job_store,
            metrics,
        )

        assert metrics.increments == []
        assert metrics.observations == []

    @pytest.mark.asyncio
    async def test_run_crawl_job_ignores_unknown_progress_status(
        self, monkeypatch, tmp_path
    ):
        from article_extractor.crawler import CrawlProgress
        from article_extractor.server import CrawlJobStore, _run_crawl_job
        from article_extractor.types import CrawlConfig, CrawlManifest, NetworkOptions

        class _Metrics:
            def __init__(self):
                self.enabled = True
                self.increments = []
                self.observations = []

            def increment(self, name, tags=None):
                self.increments.append((name, tags))

            def observe(self, name, value=None, tags=None):
                self.observations.append((name, value, tags))

        async def _fake_run_crawl(config, network=None, on_progress=None):
            if on_progress:
                on_progress(
                    CrawlProgress(
                        url="https://example.com/a",
                        status="other",
                        fetched=1,
                        successful=0,
                        failed=0,
                        skipped=0,
                        remaining=0,
                    )
                )
            return CrawlManifest(
                job_id="job-1",
                started_at="start",
                completed_at="end",
                config=config,
                total_pages=1,
                successful=0,
                failed=0,
                skipped=0,
                duration_seconds=1.5,
            )

        monkeypatch.setattr("article_extractor.crawler.run_crawl", _fake_run_crawl)

        job_store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com/"])
        job = await job_store.create_job(config)
        metrics = _Metrics()

        await _run_crawl_job(
            job.job_id,
            config,
            NetworkOptions(),
            job_store,
            metrics,
        )

        assert metrics.increments == []

    @pytest.mark.asyncio
    async def test_run_crawl_job_handles_failure(self, monkeypatch, tmp_path):
        from article_extractor.server import CrawlJobStore, _run_crawl_job
        from article_extractor.types import CrawlConfig, NetworkOptions

        class _Metrics:
            def __init__(self):
                self.enabled = True
                self.increments = []

            def increment(self, name, tags=None):
                self.increments.append((name, tags))

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("article_extractor.crawler.run_crawl", _boom)

        job_store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com/"])
        job = await job_store.create_job(config)
        metrics = _Metrics()

        await _run_crawl_job(
            job.job_id,
            config,
            NetworkOptions(),
            job_store,
            metrics,
        )

        updated = await job_store.get_job(job.job_id)
        assert updated.status == "failed"
        assert updated.error == "boom"
        assert metrics.increments

    @pytest.mark.asyncio
    async def test_run_crawl_job_failure_skips_metrics_when_disabled(
        self, monkeypatch, tmp_path
    ):
        from article_extractor.server import CrawlJobStore, _run_crawl_job
        from article_extractor.types import CrawlConfig, NetworkOptions

        class _Metrics:
            def __init__(self):
                self.enabled = False
                self.increments = []

            def increment(self, name, tags=None):
                self.increments.append((name, tags))

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("article_extractor.crawler.run_crawl", _boom)

        job_store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com/"])
        job = await job_store.create_job(config)
        metrics = _Metrics()

        await _run_crawl_job(
            job.job_id,
            config,
            NetworkOptions(),
            job_store,
            metrics,
        )

        assert metrics.increments == []


def test_crawl_job_store_ignores_missing_job():
    from article_extractor.server import CrawlJobStore

    store = CrawlJobStore()

    asyncio.run(store.update_job("missing", status="running"))


def test_crawl_job_store_get_task_missing():
    from article_extractor.server import CrawlJobStore

    store = CrawlJobStore()

    assert store.get_task("missing") is None


def test_submit_crawl_requires_service_initialized(client, monkeypatch):
    monkeypatch.setattr(app.state, "crawl_jobs", None, raising=False)

    response = client.post(
        "/crawl",
        json={"output_dir": "/tmp/crawl-test", "seeds": ["https://example.com"]},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Crawl service not initialized"


def test_submit_crawl_respects_concurrency_limit(client, monkeypatch):
    class _LimitedStore:
        async def can_start(self):
            return False

    monkeypatch.setattr(app.state, "crawl_jobs", _LimitedStore(), raising=False)

    response = client.post(
        "/crawl",
        json={"output_dir": "/tmp/crawl-test", "seeds": ["https://example.com"]},
    )

    assert response.status_code == 429


def test_get_crawl_status_requires_service_initialized(client, monkeypatch):
    monkeypatch.setattr(app.state, "crawl_jobs", None, raising=False)

    response = client.get("/crawl/any-job")

    assert response.status_code == 503
    assert response.json()["detail"] == "Crawl service not initialized"


def test_get_crawl_status_returns_job(client, monkeypatch, tmp_path):
    from article_extractor.server import CrawlJobStore
    from article_extractor.types import CrawlConfig

    store = CrawlJobStore()
    config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
    job = asyncio.run(store.create_job(config))
    job.status = "running"
    job.progress = 2
    job.total = 4
    job._successful = 2
    job._failed = 1
    job._skipped = 0
    monkeypatch.setattr(app.state, "crawl_jobs", store, raising=False)

    response = client.get(f"/crawl/{job.job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == job.job_id
    assert payload["status"] == "running"
    assert payload["progress"] == 2
    assert payload["total"] == 4
    assert payload["successful"] == 2
    assert payload["failed"] == 1


def test_get_crawl_manifest_requires_service_initialized(client, monkeypatch):
    monkeypatch.setattr(app.state, "crawl_jobs", None, raising=False)

    response = client.get("/crawl/any-job/manifest")

    assert response.status_code == 503
    assert response.json()["detail"] == "Crawl service not initialized"


def test_get_crawl_manifest_rejects_incomplete_job(client, monkeypatch, tmp_path):
    from article_extractor.server import CrawlJobStore
    from article_extractor.types import CrawlConfig

    store = CrawlJobStore()
    config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
    job = asyncio.run(store.create_job(config))
    job.status = "running"
    monkeypatch.setattr(app.state, "crawl_jobs", store, raising=False)

    response = client.get(f"/crawl/{job.job_id}/manifest")

    assert response.status_code == 400


def test_get_crawl_manifest_missing_file(client, monkeypatch, tmp_path):
    from article_extractor.server import CrawlJobStore
    from article_extractor.types import CrawlConfig

    store = CrawlJobStore()
    config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
    job = asyncio.run(store.create_job(config))
    job.status = "completed"
    monkeypatch.setattr(app.state, "crawl_jobs", store, raising=False)

    response = client.get(f"/crawl/{job.job_id}/manifest")

    assert response.status_code == 404


def test_get_crawl_manifest_returns_file(client, monkeypatch, tmp_path):
    from article_extractor.server import CrawlJobStore
    from article_extractor.types import CrawlConfig

    store = CrawlJobStore()
    config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
    job = asyncio.run(store.create_job(config))
    job.status = "completed"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"ok": true}', encoding="utf-8")
    monkeypatch.setattr(app.state, "crawl_jobs", store, raising=False)

    response = client.get(f"/crawl/{job.job_id}/manifest")

    assert response.status_code == 200
    assert response.text.strip() == '{"ok": true}'
