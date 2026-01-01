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
import os
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

from .extractor import extract_article_from_url
from .types import ExtractionOptions

logger = logging.getLogger(__name__)

DEFAULT_CACHE_SIZE = 1000
CACHE_SIZE_ENV = "ARTICLE_EXTRACTOR_CACHE_SIZE"
THREADPOOL_ENV = "ARTICLE_EXTRACTOR_THREADPOOL_SIZE"


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
    raw = os.environ.get(CACHE_SIZE_ENV)
    if raw is None:
        return DEFAULT_CACHE_SIZE
    try:
        return max(1, int(raw))
    except ValueError:
        logger.warning(
            "Invalid %s=%s, falling back to %s", CACHE_SIZE_ENV, raw, DEFAULT_CACHE_SIZE
        )
        return DEFAULT_CACHE_SIZE


def _determine_threadpool_size() -> int:
    default_workers = max(4, (os.cpu_count() or 1) * 2)
    raw = os.environ.get(THREADPOOL_ENV)
    if raw is None:
        return default_workers
    try:
        requested = int(raw)
    except ValueError:
        logger.warning(
            "Invalid %s=%s, falling back to %s", THREADPOOL_ENV, raw, default_workers
        )
        return default_workers
    return default_workers if requested <= 0 else requested


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage shared resources like cache and threadpool."""

    cache = ExtractionResponseCache(_read_cache_size())
    cache_lock = asyncio.Lock()
    threadpool = ThreadPoolExecutor(
        max_workers=_determine_threadpool_size(),
        thread_name_prefix="article-extractor",
    )

    app.state.cache = cache
    app.state.cache_lock = cache_lock
    app.state.threadpool = threadpool

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


# Request/Response models
class ExtractionRequest(BaseModel):
    """Request model for article extraction."""

    url: Annotated[HttpUrl, Field(description="URL to extract article content from")]


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
        logger.info(f"Extracting article from: {url}")

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
            logger.debug("Cache hit for %s", url)
            return cached

        # Extract article using default options
        result = await extract_article_from_url(
            url,
            options=options,
            executor=getattr(request.app.state, "threadpool", None),
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
        logger.exception("Unexpected error extracting article from %s", url)
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
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "url": str(request.url)},
    )


@app.exception_handler(Exception)
async def general_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.exception("Unexpected error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": f"{exc!s}"},
    )
