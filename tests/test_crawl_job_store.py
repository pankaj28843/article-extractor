"""Tests for crawl_job_store module."""

from __future__ import annotations

import asyncio

import pytest

from article_extractor.crawl_job_store import CrawlJobStore
from article_extractor.types import CrawlConfig, CrawlManifest


class TestCrawlJobStore:
    """Tests for CrawlJobStore class."""

    @pytest.mark.asyncio
    async def test_create_job_assigns_unique_id(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
        job = await store.create_job(config)

        assert job.job_id is not None
        assert len(job.job_id) == 36  # UUID4 format
        assert job.status == "queued"
        assert job.config == config

    @pytest.mark.asyncio
    async def test_create_multiple_jobs_get_unique_ids(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://test.com"])

        job1 = await store.create_job(config)
        job2 = await store.create_job(config)

        assert job1.job_id != job2.job_id

    @pytest.mark.asyncio
    async def test_get_job_returns_created_job(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
        created = await store.create_job(config)

        fetched = await store.get_job(created.job_id)

        assert fetched is not None
        assert fetched.job_id == created.job_id
        assert fetched.status == "queued"

    @pytest.mark.asyncio
    async def test_get_job_returns_none_for_missing(self):
        store = CrawlJobStore()
        assert await store.get_job("nonexistent-id") is None

    @pytest.mark.asyncio
    async def test_update_job_updates_status(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
        job = await store.create_job(config)

        await store.update_job(job.job_id, status="running")

        updated = await store.get_job(job.job_id)
        assert updated.status == "running"

    @pytest.mark.asyncio
    async def test_update_job_updates_progress_fields(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
        job = await store.create_job(config)

        await store.update_job(job.job_id, progress=5, total=10, successful=4, failed=1)

        updated = await store.get_job(job.job_id)
        assert updated.progress == 5
        assert updated.total == 10
        assert updated._successful == 4
        assert updated._failed == 1

    @pytest.mark.asyncio
    async def test_update_job_ignores_missing_job(self):
        store = CrawlJobStore()
        # Should not raise, just silently skip
        await store.update_job("missing-id", status="running")

    @pytest.mark.asyncio
    async def test_update_job_partial_updates(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
        job = await store.create_job(config)

        await store.update_job(job.job_id, progress=10)
        updated = await store.get_job(job.job_id)
        assert updated.progress == 10
        assert updated.status == "queued"  # Not changed

        await store.update_job(job.job_id, status="completed")
        updated = await store.get_job(job.job_id)
        assert updated.status == "completed"
        assert updated.progress == 10  # Preserved

    @pytest.mark.asyncio
    async def test_store_and_get_manifest(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
        job = await store.create_job(config)
        manifest = CrawlManifest(
            job_id=job.job_id,
            started_at="2024-01-01T00:00:00Z",
            completed_at="2024-01-01T01:00:00Z",
            config=config,
            total_pages=10,
            successful=8,
        )

        await store.store_manifest(job.job_id, manifest)
        retrieved = await store.get_manifest(job.job_id)

        assert retrieved is not None
        assert retrieved.job_id == job.job_id
        assert retrieved.started_at == manifest.started_at
        assert retrieved.successful == 8

    @pytest.mark.asyncio
    async def test_get_manifest_returns_none_for_missing(self):
        store = CrawlJobStore()
        assert await store.get_manifest("nonexistent") is None

    @pytest.mark.asyncio
    async def test_running_count_empty_initially(self):
        store = CrawlJobStore()
        assert await store.running_count() == 0

    @pytest.mark.asyncio
    async def test_running_count_counts_running_jobs(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])

        job1 = await store.create_job(config)
        job2 = await store.create_job(config)
        job3 = await store.create_job(config)

        await store.update_job(job1.job_id, status="running")
        await store.update_job(job2.job_id, status="running")
        await store.update_job(job3.job_id, status="completed")

        assert await store.running_count() == 2

    @pytest.mark.asyncio
    async def test_can_start_respects_max_concurrent(self, tmp_path):
        store = CrawlJobStore(max_concurrent=2)
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])

        assert await store.can_start()  # 0 running

        job1 = await store.create_job(config)
        await store.update_job(job1.job_id, status="running")
        assert await store.can_start()  # 1 running

        job2 = await store.create_job(config)
        await store.update_job(job2.job_id, status="running")
        assert not await store.can_start()  # 2 running (at limit)

    @pytest.mark.asyncio
    async def test_register_and_get_task(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])
        job = await store.create_job(config)

        async def dummy_task():
            await asyncio.sleep(0.01)

        task = asyncio.create_task(dummy_task())
        store.register_task(job.job_id, task)

        retrieved = store.get_task(job.job_id)
        assert retrieved is task

        await task  # Clean up

    @pytest.mark.asyncio
    async def test_get_task_returns_none_for_missing(self):
        store = CrawlJobStore()
        assert store.get_task("nonexistent") is None

    @pytest.mark.asyncio
    async def test_concurrent_operations_are_safe(self, tmp_path):
        store = CrawlJobStore()
        config = CrawlConfig(output_dir=tmp_path, seeds=["https://example.com"])

        async def create_and_update(i):
            job = await store.create_job(config)
            await store.update_job(job.job_id, status="running", progress=i)
            return job

        jobs = await asyncio.gather(*[create_and_update(i) for i in range(10)])

        assert len(jobs) == 10
        assert len({j.job_id for j in jobs}) == 10  # All unique IDs
        assert await store.running_count() == 10
