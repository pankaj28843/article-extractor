"""Tests for storage_queue module."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from article_extractor.storage_queue import (
    StorageChangeDoc,
    StorageQueue,
    capture_snapshot,
    normalize_payload,
)


def test_storage_queue_merge_applies_latest_payload(tmp_path):
    storage_file = tmp_path / "storage_state.json"
    queue = StorageQueue(storage_file)

    queue.enqueue(normalize_payload({"cookies": ["first"]}))
    queue.enqueue(normalize_payload({"cookies": ["second"]}))

    stats = queue.merge()

    assert stats.pending == 2
    payload = json.loads(storage_file.read_text(encoding="utf-8"))
    assert payload["cookies"] == ["second"]
    # Snapshot should now exist
    snapshot = capture_snapshot(storage_file)
    assert snapshot is not None
    assert snapshot.size == len(storage_file.read_bytes())


def test_storage_queue_logs_thresholds(tmp_path, caplog, monkeypatch):
    storage_file = tmp_path / "state.json"
    queue = StorageQueue(
        storage_file,
        max_entries=1,
        max_age_seconds=0.1,
    )

    # Freeze time to simulate backlog age
    times = iter([0.0, 0.0, 1.0, 1.0, 1.0])

    def _fake_time():
        try:
            return next(times)
        except StopIteration:  # pragma: no cover - defensive guard
            return 1.0

    monkeypatch.setattr("article_extractor.storage_queue.time.time", _fake_time)

    queue.enqueue(normalize_payload({"cookies": ["old"]}))
    queue.enqueue(normalize_payload({"cookies": ["new"]}))

    caplog.set_level("CRITICAL")
    queue.merge()

    assert any(
        "Storage queue depth exceeded threshold" in record.message
        for record in caplog.records
    )
    assert any(
        "Storage queue backlog age exceeded threshold" in record.message
        for record in caplog.records
    )


def test_capture_snapshot_returns_none_when_missing(tmp_path):
    target = tmp_path / "missing.json"

    assert capture_snapshot(target) is None


def test_storage_queue_merge_without_docs_returns_empty_stats(tmp_path):
    queue = StorageQueue(tmp_path / "state.json")

    stats = queue.merge()

    assert stats.pending == 0
    assert stats.oldest_age is None


def test_storage_queue_handles_invalid_change_doc(tmp_path, caplog):
    queue = StorageQueue(tmp_path / "state.json")
    bad_doc = queue.queue_dir / "invalid.json"
    bad_doc.write_text("{", encoding="utf-8")

    caplog.set_level("WARNING")
    docs = queue._load_pending_docs()

    assert docs == []
    assert any("Failed to parse storage change" in msg for msg in caplog.messages)


def test_storage_queue_build_stats_reports_age(tmp_path):
    queue = StorageQueue(tmp_path / "state.json")
    now = time.time()
    docs = [
        StorageChangeDoc(
            path=Path("old.json"),
            change_id="old",
            created_at=now - 5,
            fingerprint="abc",
            hostname=None,
            pid=None,
            worker=None,
            payload=b"{}",
        ),
        StorageChangeDoc(
            path=Path("new.json"),
            change_id="new",
            created_at=now - 1,
            fingerprint="def",
            hostname=None,
            pid=None,
            worker=None,
            payload=b"{}",
        ),
    ]

    stats = queue._build_stats(docs)

    assert stats.pending == 2
    assert stats.newest_change_id == "new"
    assert stats.oldest_age == pytest.approx(5, rel=0.2)


def test_storage_queue_prune_processed_removes_old_entries(tmp_path):
    queue = StorageQueue(tmp_path / "state.json", processed_retention_seconds=0.01)
    processed = queue.processed_dir / "stale.json"
    processed.write_text("{}", encoding="utf-8")
    old_time = time.time() - 10
    os.utime(processed, (old_time, old_time))

    queue._prune_processed()

    assert not processed.exists()


def test_storage_queue_prune_processed_skips_when_disabled(tmp_path):
    queue = StorageQueue(tmp_path / "state.json", processed_retention_seconds=0.0)

    queue._prune_processed()


def test_normalize_payload_handles_various_types():
    assert normalize_payload("hello") == b"hello"
    payload = normalize_payload({"foo": "bar"})

    assert json.loads(payload.decode("utf-8")) == {"foo": "bar"}


def test_normalize_payload_keeps_bytes():
    assert normalize_payload(b"payload") == b"payload"
