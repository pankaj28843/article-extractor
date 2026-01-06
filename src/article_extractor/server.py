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
from fastapi.responses import FileResponse, JSONResponse
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
from .types import (
    CrawlConfig,
    CrawlJob,
    CrawlManifest,
    ExtractionOptions,
    NetworkOptions,
)

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
    app.state.crawl_jobs = CrawlJobStore(max_concurrent=1)
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
        description=(
            "Optional filesystem path to persist Playwright storage_state.json; "
            "omit for the default ephemeral context"
        ),
    )


# --- Crawl API Models ---


class CrawlRequest(BaseModel):
    """Request model for submitting a crawl job."""

    output_dir: str = Field(description="Output directory for extracted Markdown files")
    seeds: list[str] = Field(
        default_factory=list, description="Seed URLs to start crawling"
    )
    sitemaps: list[str] = Field(
        default_factory=list, description="Sitemap URLs or local paths"
    )
    allow_prefixes: list[str] = Field(
        default_factory=list, description="URL prefixes to allow"
    )
    deny_prefixes: list[str] = Field(
        default_factory=list, description="URL prefixes to deny"
    )
    max_pages: int = Field(
        default=100, ge=1, le=10000, description="Maximum pages to crawl"
    )
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum BFS depth")
    concurrency: int = Field(default=5, ge=1, le=20, description="Concurrent requests")
    rate_limit_delay: float = Field(
        default=1.0, ge=0.0, description="Seconds between requests per host"
    )
    follow_links: bool = Field(default=True, description="Discover and follow links")
    network: NetworkRequest | None = Field(
        default=None, description="Network configuration"
    )


class CrawlJobResponse(BaseModel):
    """Response model for crawl job status."""

    job_id: str = Field(description="Unique job identifier")
    status: str = Field(description="Job status: queued, running, completed, failed")
    progress: int = Field(description="Pages processed so far")
    total: int = Field(description="Estimated total pages (may increase during crawl)")
    successful: int = Field(default=0, description="Successfully extracted pages")
    failed: int = Field(default=0, description="Failed pages")
    skipped: int = Field(default=0, description="Skipped pages")
    error: str | None = Field(default=None, description="Error message if failed")
    started_at: str | None = Field(
        default=None, description="ISO timestamp when job started"
    )
    completed_at: str | None = Field(
        default=None, description="ISO timestamp when job completed"
    )


class CrawlJobStore:
    """In-memory store for tracking crawl jobs."""

    def __init__(self, max_concurrent: int = 1) -> None:
        self.max_concurrent = max_concurrent
        self._jobs: dict[str, CrawlJob] = {}
        self._manifests: dict[str, CrawlManifest] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def get_job(self, job_id: str) -> CrawlJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def get_manifest(self, job_id: str) -> CrawlManifest | None:
        async with self._lock:
            return self._manifests.get(job_id)

    async def create_job(self, config: CrawlConfig) -> CrawlJob:
        import uuid

        job_id = str(uuid.uuid4())
        job = CrawlJob(job_id=job_id, config=config, status="queued")
        async with self._lock:
            self._jobs[job_id] = job
        return job

    async def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        total: int | None = None,
        successful: int | None = None,
        failed: int | None = None,
        skipped: int | None = None,
        error: str | None = None,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if total is not None:
                job.total = total
            if successful is not None:
                # Store in a custom attribute since CrawlJob doesn't have these
                job._successful = successful
            if failed is not None:
                job._failed = failed
            if skipped is not None:
                job._skipped = skipped
            if error is not None:
                job.error = error
            if started_at is not None:
                job.started_at = started_at
            if completed_at is not None:
                job.completed_at = completed_at

    async def store_manifest(self, job_id: str, manifest: CrawlManifest) -> None:
        async with self._lock:
            self._manifests[job_id] = manifest

    async def running_count(self) -> int:
        async with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == "running")

    async def can_start(self) -> bool:
        return await self.running_count() < self.max_concurrent

    def register_task(self, job_id: str, task: asyncio.Task) -> None:
        self._tasks[job_id] = task

    def get_task(self, job_id: str) -> asyncio.Task | None:
        return self._tasks.get(job_id)


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
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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


# --- Crawl API Endpoints ---


async def _run_crawl_job(
    job_id: str,
    config: CrawlConfig,
    network: NetworkOptions,
    job_store: CrawlJobStore,
    metrics_emitter,
) -> None:
    """Execute a crawl job in the background."""
    from datetime import UTC, datetime

    from .crawler import CrawlProgress, run_crawl

    started_at = datetime.now(UTC).isoformat()
    await job_store.update_job(job_id, status="running", started_at=started_at)

    logger.info(
        "Starting crawl job",
        extra={"job_id": job_id, "seeds": config.seeds, "sitemaps": config.sitemaps},
    )

    # Track background update tasks to avoid GC issues
    _background_tasks: set[asyncio.Task] = set()

    def on_progress(progress: CrawlProgress) -> None:
        # Fire-and-forget update (we can't await inside sync callback)
        task = asyncio.create_task(
            job_store.update_job(
                job_id,
                progress=progress.fetched,
                total=progress.fetched + progress.remaining,
                successful=progress.successful,
                failed=progress.failed,
                skipped=progress.skipped,
            )
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        # Emit metrics
        if metrics_emitter and getattr(metrics_emitter, "enabled", False):
            if progress.status == "success":
                metrics_emitter.increment(
                    "crawler_pages_total", tags={"status": "success"}
                )
            elif progress.status == "failed":
                metrics_emitter.increment(
                    "crawler_pages_total", tags={"status": "failed"}
                )
            elif progress.status == "skipped":
                metrics_emitter.increment(
                    "crawler_pages_total", tags={"status": "skipped"}
                )

    try:
        manifest = await run_crawl(config, network=network, on_progress=on_progress)
        await job_store.store_manifest(job_id, manifest)

        completed_at = datetime.now(UTC).isoformat()
        await job_store.update_job(
            job_id,
            status="completed",
            completed_at=completed_at,
            progress=manifest.total_pages,
            total=manifest.total_pages,
            successful=manifest.successful,
            failed=manifest.failed,
            skipped=manifest.skipped,
        )

        # Emit duration metric
        if metrics_emitter and getattr(metrics_emitter, "enabled", False):
            metrics_emitter.observe(
                "crawler_duration_seconds",
                value=manifest.duration_seconds,
                tags={"status": "completed"},
            )

        logger.info(
            "Crawl job completed",
            extra={
                "job_id": job_id,
                "total": manifest.total_pages,
                "successful": manifest.successful,
                "failed": manifest.failed,
                "duration_seconds": manifest.duration_seconds,
            },
        )

    except Exception as exc:
        logger.exception("Crawl job failed", extra={"job_id": job_id})
        completed_at = datetime.now(UTC).isoformat()
        await job_store.update_job(
            job_id,
            status="failed",
            completed_at=completed_at,
            error=str(exc),
        )

        # Emit failure metric
        if metrics_emitter and getattr(metrics_emitter, "enabled", False):
            metrics_emitter.increment("crawler_jobs_total", tags={"status": "failed"})


@app.post(
    "/crawl", response_model=CrawlJobResponse, status_code=status.HTTP_202_ACCEPTED
)
async def submit_crawl_job(
    crawl_request: CrawlRequest,
    request: Request,
) -> CrawlJobResponse:
    """Submit a new crawl job.

    The job runs in the background. Use GET /crawl/{job_id} to poll status.

    Args:
        crawl_request: Crawl configuration including required output_dir.

    Returns:
        Job ID and initial status.

    Raises:
        HTTPException: 400 if output_dir invalid, 429 if too many concurrent jobs.
    """
    from pathlib import Path

    from .crawler import validate_output_dir

    request_id = getattr(request.state, "request_id", None)

    # Validate output_dir
    output_path = Path(crawl_request.output_dir)
    try:
        validate_output_dir(output_path, create=True)
    except (ValueError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid output_dir: {exc}",
        ) from exc

    # Check if we have seeds or sitemaps
    if not crawl_request.seeds and not crawl_request.sitemaps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one seed URL or sitemap is required",
        )

    # Check concurrent job limit
    job_store: CrawlJobStore = getattr(request.app.state, "crawl_jobs", None)
    if job_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Crawl service not initialized",
        )

    if not await job_store.can_start():
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum concurrent crawl jobs reached. Try again later.",
        )

    # Build config
    config = CrawlConfig(
        output_dir=output_path,
        seeds=crawl_request.seeds,
        sitemaps=crawl_request.sitemaps,
        allow_prefixes=crawl_request.allow_prefixes,
        deny_prefixes=crawl_request.deny_prefixes,
        max_pages=crawl_request.max_pages,
        max_depth=crawl_request.max_depth,
        concurrency=crawl_request.concurrency,
        rate_limit_delay=crawl_request.rate_limit_delay,
        follow_links=crawl_request.follow_links,
    )

    # Resolve network options
    network_payload = crawl_request.network
    base: NetworkOptions | None = getattr(request.app.state, "network_defaults", None)
    network = resolve_network_options(
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

    # Create job
    job = await job_store.create_job(config)
    metrics_emitter = getattr(request.app.state, "metrics_emitter", None)

    # Start background task
    task = asyncio.create_task(
        _run_crawl_job(job.job_id, config, network, job_store, metrics_emitter)
    )
    job_store.register_task(job.job_id, task)

    logger.info(
        "Crawl job submitted",
        extra={"job_id": job.job_id, "request_id": request_id},
    )

    return CrawlJobResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        total=job.total,
    )


@app.get("/crawl/{job_id}", response_model=CrawlJobResponse)
async def get_crawl_job_status(job_id: str, request: Request) -> CrawlJobResponse:
    """Get the status of a crawl job.

    Args:
        job_id: The job identifier returned from POST /crawl.

    Returns:
        Current job status and progress.

    Raises:
        HTTPException: 404 if job not found.
    """
    job_store: CrawlJobStore = getattr(request.app.state, "crawl_jobs", None)
    if job_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Crawl service not initialized",
        )

    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return CrawlJobResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        total=job.total,
        successful=getattr(job, "_successful", 0),
        failed=getattr(job, "_failed", 0),
        skipped=getattr(job, "_skipped", 0),
        error=job.error,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@app.get("/crawl/{job_id}/manifest")
async def get_crawl_manifest(job_id: str, request: Request) -> FileResponse:
    """Download the manifest.json for a completed crawl job.

    Args:
        job_id: The job identifier.

    Returns:
        The manifest.json file.

    Raises:
        HTTPException: 404 if job not found, 400 if job not completed.
    """
    job_store: CrawlJobStore = getattr(request.app.state, "crawl_jobs", None)
    if job_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Crawl service not initialized",
        )

    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    if job.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job {job_id} is not completed (status: {job.status})",
        )

    manifest_path = job.config.output_dir / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manifest file not found for job {job_id}",
        )

    return FileResponse(
        path=str(manifest_path),
        media_type="application/json",
        filename=f"manifest-{job_id}.json",
    )


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
