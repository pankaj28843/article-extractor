"""In-memory store for tracking crawl jobs.

Provides thread-safe async operations for managing crawl job lifecycle,
including job creation, status updates, and manifest storage.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .types import CrawlConfig, CrawlJob, CrawlManifest


class CrawlJobStore:
    """In-memory store for tracking crawl jobs.

    Manages job lifecycle with async-safe operations for concurrent access.
    Tracks job metadata, manifests, and associated async tasks.
    """

    def __init__(self, max_concurrent: int = 1) -> None:
        """Initialize job store.

        Args:
            max_concurrent: Maximum number of concurrent running jobs
        """
        self.max_concurrent = max_concurrent
        self._jobs: dict[str, CrawlJob] = {}
        self._manifests: dict[str, CrawlManifest] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def get_job(self, job_id: str) -> CrawlJob | None:
        """Retrieve job by ID.

        Args:
            job_id: Unique job identifier

        Returns:
            CrawlJob if found, None otherwise
        """
        async with self._lock:
            return self._jobs.get(job_id)

    async def get_manifest(self, job_id: str) -> CrawlManifest | None:
        """Retrieve crawl manifest for a job.

        Args:
            job_id: Unique job identifier

        Returns:
            CrawlManifest if found, None otherwise
        """
        async with self._lock:
            return self._manifests.get(job_id)

    async def create_job(self, config: CrawlConfig) -> CrawlJob:
        """Create a new crawl job.

        Args:
            config: Crawl configuration

        Returns:
            Newly created CrawlJob with generated ID
        """
        from .types import CrawlJob

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
        """Update job fields.

        Args:
            job_id: Unique job identifier
            status: New job status
            progress: Pages processed
            total: Total estimated pages
            successful: Successfully extracted pages
            failed: Failed pages
            skipped: Skipped pages
            error: Error message
            started_at: ISO timestamp when job started
            completed_at: ISO timestamp when job completed
        """
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
        """Store crawl manifest for a job.

        Args:
            job_id: Unique job identifier
            manifest: Crawl manifest to store
        """
        async with self._lock:
            self._manifests[job_id] = manifest

    async def running_count(self) -> int:
        """Count currently running jobs.

        Returns:
            Number of jobs with status 'running'
        """
        async with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == "running")

    async def can_start(self) -> bool:
        """Check if a new job can start.

        Returns:
            True if running count is below max_concurrent limit
        """
        return await self.running_count() < self.max_concurrent

    def register_task(self, job_id: str, task: asyncio.Task) -> None:
        """Register async task for a job.

        Args:
            job_id: Unique job identifier
            task: Async task handling the job
        """
        self._tasks[job_id] = task

    def get_task(self, job_id: str) -> asyncio.Task | None:
        """Retrieve async task for a job.

        Args:
            job_id: Unique job identifier

        Returns:
            Async task if registered, None otherwise
        """
        return self._tasks.get(job_id)
