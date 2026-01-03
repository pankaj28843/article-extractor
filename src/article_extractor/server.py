"""FastAPI HTTP server for article extraction.

This server provides a drop-in replacement for readability-js-server with
the same API but using pure Python instead of Node.js.

Example:
    Run the server:
        uvicorn article_extractor.server:app --host 0.0.0.0 --port 3000

    Query the server:
        curl -XPOST http://localhost:3000/ \\
            -H "Content-Type: application/json" \\
            -d'{"url": "https://en.wikipedia.org/wiki/Wikipedia"}'
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

from .extractor import extract_article_from_url
from .network import resolve_network_options
from .observability import (
    build_metrics_emitter,
    generate_request_id,
    setup_logging,
    strip_url,
)
from .settings import ServiceSettings, get_settings
from .types import ExtractionOptions, NetworkOptions

logger = logging.getLogger(__name__)


def _configure_logging(settings: ServiceSettings | None = None) -> None:
    """Initialize structured logging using the latest ServiceSettings."""

    resolved = settings or get_settings()
    setup_logging(
        component="server",
        level=resolved.log_level,
        default_level="INFO",
        log_format=resolved.log_format,
    )


_configure_logging()


class ExtractionResponseCache:
    """Simple in-memory LRU cache for extraction responses."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max(1, max_size)
        self._store: OrderedDict[str, ExtractionResponse] = OrderedDict()

    def get(self, key: str) -> ExtractionResponse | None:
        value = self._store.get(key)
        if value is not None:
            self._store.move_to_end(key)
        return value

    def set(self, key: str, value: ExtractionResponse) -> None:
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()


def _read_cache_size() -> int:
    return get_settings().cache_size


def _determine_threadpool_size(settings: ServiceSettings | None = None) -> int:
    settings = settings or get_settings()
    return settings.determine_threadpool_size()


def _initialize_state_from_env(state) -> None:
    settings = get_settings()
    if getattr(state, "network_defaults", None) is None:
        env_mapping = settings.build_network_env()
        state.network_defaults = resolve_network_options(env=env_mapping)
    if not hasattr(state, "prefer_playwright") or state.prefer_playwright is None:
        state.prefer_playwright = _read_prefer_playwright_env()


def _read_prefer_playwright_env(_default: bool = True) -> bool:
    return get_settings().prefer_playwright


def _emit_request_metrics(
    state,
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> None:
    emitter = getattr(state, "metrics_emitter", None)
    if emitter is None or not getattr(emitter, "enabled", False):
        return
    path_value = path or "/"
    status_bucket = f"{int(status_code) // 100}xx"
    tags = {
        "method": method,
        "status": str(status_code),
        "path": path_value,
        "status_group": status_bucket,
    }
    emitter.increment("server_http_requests_total", tags=tags)
    emitter.observe(
        "server_http_request_duration_ms",
        value=duration_ms,
        tags=tags,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage shared resources like cache and threadpool."""

    settings = get_settings()
    cache = ExtractionResponseCache(settings.cache_size)
    cache_lock = asyncio.Lock()
    threadpool = ThreadPoolExecutor(
        max_workers=_determine_threadpool_size(settings),
        thread_name_prefix="article-extractor",
    )

    app.state.cache = cache
    app.state.cache_lock = cache_lock
    app.state.threadpool = threadpool
    app.state.log_diagnostics = settings.log_diagnostics
    app.state.metrics_emitter = build_metrics_emitter(
        component="server",
        enabled=settings.metrics_enabled,
        sink=settings.metrics_sink,
        statsd_host=settings.metrics_statsd_host,
        statsd_port=settings.metrics_statsd_port,
        namespace=settings.metrics_namespace,
    )
    _initialize_state_from_env(app.state)

    try:
        yield
    finally:
        cache.clear()
        threadpool.shutdown(wait=True)


# Create FastAPI app
app = FastAPI(
    title="Article Extractor Server",
    description="Pure-Python article extraction service - Drop-in replacement for readability-js-server",
    version="0.1.2",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context_logging(request: Request, call_next):
    request_id = generate_request_id(request.headers.get("x-request-id"))
    request.state.request_id = request_id
    start = time.perf_counter()
    url_hint = strip_url(str(request.url))
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.exception(
            "Request failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "duration_ms": duration_ms,
                "url": url_hint,
            },
        )
        _emit_request_metrics(
            request.app.state,
            method=request.method,
            path=request.url.path,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            duration_ms=duration_ms,
        )
        raise

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "Request complete",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "url": url_hint,
        },
    )
    _emit_request_metrics(
        request.app.state,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


# Request/Response models
class ExtractionRequest(BaseModel):
    """Request model for article extraction."""

    url: Annotated[HttpUrl, Field(description="URL to extract article content from")]
    prefer_playwright: bool | None = Field(
        default=None, description="Prefer Playwright fetcher when available"
    )
    network: NetworkRequest | None = Field(
        default=None, description="Optional networking overrides"
    )


class ExtractionResponse(BaseModel):
    """Response model matching readability-js-server format."""

    url: str = Field(description="Original URL")
    title: str = Field(description="Extracted article title")
    byline: str | None = Field(default=None, description="Article author")
    dir: str = Field(default="ltr", description="Text direction (ltr/rtl)")
    content: str = Field(description="Extracted HTML content")
    length: int = Field(description="Character length of content")
    excerpt: str = Field(description="Short text excerpt")
    siteName: str | None = Field(default=None, description="Site name (if available)")

    # Additional fields from article-extractor
    markdown: str = Field(description="Markdown version of content")
    word_count: int = Field(description="Word count of content")
    success: bool = Field(description="Whether extraction succeeded")


class NetworkRequest(BaseModel):
    """Network configuration overrides accepted by the server."""

    user_agent: str | None = Field(
        default=None, description="Explicit User-Agent header"
    )
    random_user_agent: bool | None = Field(
        default=None, description="Randomize User-Agent via fake-useragent"
    )
    proxy: str | None = Field(
        default=None, description="Proxy URL overriding HTTP(S)_PROXY env"
    )
    proxy_bypass: list[str] | None = Field(
        default=None,
        description="Hosts or domains that should bypass the configured proxy",
    )
    headed: bool | None = Field(
        default=None, description="Launch Playwright in headed mode"
    )
    user_interaction_timeout: float | None = Field(
        default=None,
        ge=0.0,
        description="Seconds to pause for manual interaction when headed",
    )
    storage_state: str | None = Field(
        default=None,
        description="Filesystem path for Playwright storage_state.json",
    )


@app.get("/", status_code=status.HTTP_200_OK)
async def root() -> dict:
    """Health check endpoint."""
    return {
        "service": "article-extractor-server",
        "status": "running",
        "version": "0.1.2",
        "description": "Pure-Python replacement for readability-js-server",
    }


def _build_cache_key(url: str, options: ExtractionOptions) -> str:
    """Build a cache key that accounts for extraction options."""

    return "|".join(
        [
            url,
            str(options.min_word_count),
            str(options.min_char_threshold),
            "1" if options.include_images else "0",
            "1" if options.include_code_blocks else "0",
            "1" if options.safe_markdown else "0",
        ]
    )


async def _lookup_cache(request: Request, key: str) -> ExtractionResponse | None:
    cache: ExtractionResponseCache | None = getattr(request.app.state, "cache", None)
    cache_lock: asyncio.Lock | None = getattr(request.app.state, "cache_lock", None)
    if cache is None or cache_lock is None:
        return None
    async with cache_lock:
        return cache.get(key)


async def _store_cache_entry(
    request: Request, key: str, response: ExtractionResponse
) -> None:
    cache: ExtractionResponseCache | None = getattr(request.app.state, "cache", None)
    cache_lock: asyncio.Lock | None = getattr(request.app.state, "cache_lock", None)
    if cache is None or cache_lock is None:
        return
    async with cache_lock:
        cache.set(key, response)


@app.post("/", response_model=ExtractionResponse, status_code=status.HTTP_200_OK)
async def extract_article_endpoint(
    extraction_request: ExtractionRequest,
    request: Request,
) -> ExtractionResponse:
    """Extract article content from URL.

    This endpoint provides the same interface as readability-js-server.

    Args:
        extraction_request: Extraction request with URL

    Returns:
        Extracted article content in readability-js-server compatible format

    Raises:
        HTTPException: If extraction fails
    """
    try:
        url = str(extraction_request.url)
        request_id = getattr(request.state, "request_id", None)
        url_hint = strip_url(url)
        logger.info(
            "Extracting article",
            extra={"url": url_hint, "request_id": request_id},
        )

        options = ExtractionOptions(
            min_word_count=150,
            min_char_threshold=500,
            include_images=True,
            include_code_blocks=True,
            safe_markdown=True,
        )

        cache_key = _build_cache_key(url, options)
        cached = await _lookup_cache(request, cache_key)
        if cached is not None:
            logger.debug(
                "Cache hit",
                extra={"url": url_hint, "request_id": request_id},
            )
            return cached

        # Extract article using default options
        network_options = _resolve_request_network_options(extraction_request, request)
        prefer_playwright = _resolve_preference(extraction_request, request)

        result = await extract_article_from_url(
            url,
            options=options,
            network=network_options,
            prefer_playwright=prefer_playwright,
            executor=getattr(request.app.state, "threadpool", None),
            diagnostic_logging=bool(
                getattr(request.app.state, "log_diagnostics", False)
            ),
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to extract article: {result.error or 'Unknown error'}",
            )

        # Convert to readability-js-server compatible response
        response = ExtractionResponse(
            url=result.url,
            title=result.title,
            byline=result.author,
            dir="ltr",  # Could be extracted from HTML lang/dir attributes
            content=result.content,
            length=len(result.content),
            excerpt=result.excerpt,
            siteName=None,  # Could be extracted from meta tags if needed
            markdown=result.markdown,
            word_count=result.word_count,
            success=result.success,
        )
        await _store_cache_entry(request, cache_key, response)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error extracting article",
            extra={
                "url": url_hint,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        ) from e


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check(request: Request) -> dict:
    """Kubernetes/Docker health check endpoint with metadata."""
    cache: ExtractionResponseCache | None = getattr(request.app.state, "cache", None)
    threadpool: ThreadPoolExecutor | None = getattr(
        request.app.state, "threadpool", None
    )
    cache_info = {
        "size": len(cache) if cache else 0,
        "max_size": cache.max_size if cache else _read_cache_size(),
    }
    worker_info = {
        "max_workers": threadpool._max_workers
        if threadpool
        else _determine_threadpool_size(),
    }
    return {
        "status": "healthy",
        "service": "article-extractor-server",
        "version": app.version,
        "cache": cache_info,
        "worker_pool": worker_info,
    }


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    state = getattr(request, "state", None)
    request_id = getattr(state, "request_id", None) if state else None
    content = {"detail": exc.detail, "url": str(request.url)}
    if request_id:
        content["request_id"] = request_id
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers,
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    state = getattr(request, "state", None)
    request_id = getattr(state, "request_id", None) if state else None
    content = {"detail": "Internal server error", "error": f"{exc!s}"}
    if request_id:
        content["request_id"] = request_id
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=content,
        headers=headers,
    )


def configure_network_defaults(options: NetworkOptions | None) -> None:
    """Allow CLI to seed default network options for server mode."""

    settings = get_settings()
    base = options or NetworkOptions()
    app.state.network_defaults = resolve_network_options(
        base=base, env=settings.build_network_env()
    )


def set_prefer_playwright(prefer: bool) -> None:
    """Allow CLI or embedding apps to toggle fetcher preference."""

    app.state.prefer_playwright = prefer


def _resolve_request_network_options(
    extraction_request: ExtractionRequest, request: Request
) -> NetworkOptions:
    network_payload = extraction_request.network
    base: NetworkOptions | None = getattr(request.app.state, "network_defaults", None)
    return resolve_network_options(
        url=str(extraction_request.url),
        base=base,
        user_agent=network_payload.user_agent if network_payload else None,
        randomize_user_agent=(
            network_payload.random_user_agent if network_payload else None
        ),
        proxy=network_payload.proxy if network_payload else None,
        proxy_bypass=network_payload.proxy_bypass if network_payload else None,
        headed=network_payload.headed if network_payload else None,
        user_interaction_timeout=(
            network_payload.user_interaction_timeout if network_payload else None
        ),
        storage_state_path=network_payload.storage_state if network_payload else None,
    )


def _resolve_preference(
    extraction_request: ExtractionRequest, request: Request
) -> bool:
    if extraction_request.prefer_playwright is not None:
        return extraction_request.prefer_playwright
    state_value = getattr(request.app.state, "prefer_playwright", None)
    if state_value is None:
        return True
    return bool(state_value)
