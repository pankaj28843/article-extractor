"""Append-only queue for Playwright storage_state snapshots.

This module captures every browser storage mutation as an immutable document
and replays them in-order to keep a shared ``storage_state.json`` consistent
across multiple workers.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import socket
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MAX_QUEUE_ENTRIES = 20
DEFAULT_MAX_QUEUE_AGE_SECONDS = 60.0
DEFAULT_PROCESSED_RETENTION_SECONDS = 300.0


@dataclass(frozen=True)
class StorageSnapshot:
    """Fingerprint of the canonical storage file at a specific point in time."""

    path: Path
    fingerprint: str
    size: int


@dataclass(frozen=True)
class StorageChangeDoc:
    """Immutable change document persisted on disk."""

    path: Path
    change_id: str
    created_at: float
    fingerprint: str
    hostname: str | None
    pid: int | None
    worker: str | None
    payload: bytes


@dataclass(frozen=True)
class QueueStats:
    """Snapshot of queue health metrics for observability."""

    pending: int
    oldest_age: float | None
    newest_change_id: str | None


def compute_fingerprint(payload: bytes) -> str:
    """Return a deterministic SHA-256 fingerprint for payload bytes."""

    return hashlib.sha256(payload).hexdigest()


def capture_snapshot(path: Path) -> StorageSnapshot | None:
    """Read ``path`` if it exists and return a fingerprint snapshot."""

    target = Path(path).expanduser()
    if not target.exists():
        return None
    try:
        payload = target.read_bytes()
    except OSError as exc:  # pragma: no cover - best-effort diagnostics
        logger.warning(
            "Failed to read storage snapshot",
            extra={"storage_state": str(target), "error": exc.__class__.__name__},
        )
        return None
    return StorageSnapshot(
        path=target, fingerprint=compute_fingerprint(payload), size=len(payload)
    )


class StorageQueue:
    """Append-only queue that durably stores and merges storage change docs."""

    def __init__(
        self,
        storage_file: Path,
        *,
        queue_dir: Path | None = None,
        max_entries: int = DEFAULT_MAX_QUEUE_ENTRIES,
        max_age_seconds: float = DEFAULT_MAX_QUEUE_AGE_SECONDS,
        processed_retention_seconds: float = DEFAULT_PROCESSED_RETENTION_SECONDS,
    ) -> None:
        self.storage_file = Path(storage_file).expanduser()
        self.queue_dir = (
            Path(queue_dir).expanduser() if queue_dir else self._default_queue_dir()
        )
        self.max_entries = max(1, int(max_entries))
        self.max_age_seconds = max(0.0, float(max_age_seconds))
        self.processed_retention_seconds = max(0.0, float(processed_retention_seconds))
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir = self.queue_dir / "processed"
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self._hostname = socket.gethostname()

    def enqueue(
        self,
        payload: bytes,
        *,
        fingerprint: str | None = None,
        worker_id: str | None = None,
    ) -> StorageChangeDoc:
        """Persist payload bytes as an immutable document on disk."""

        fingerprint = fingerprint or compute_fingerprint(payload)
        change_id = self._next_change_id()
        created_at = time.time()
        record = {
            "change_id": change_id,
            "created_at": created_at,
            "fingerprint": fingerprint,
            "hostname": self._hostname,
            "pid": os.getpid(),
            "worker": worker_id,
            "payload": base64.b64encode(payload).decode("ascii"),
        }
        target = self.queue_dir / f"{change_id}.json"
        tmp_path = target.with_suffix(".tmp")
        serialized = json.dumps(record, separators=(",", ":"), sort_keys=True)
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(target)
        logger.debug(
            "Enqueued storage change",
            extra={
                "storage_state": str(self.storage_file),
                "change_id": change_id,
                "queue_dir": str(self.queue_dir),
                "fingerprint": fingerprint,
            },
        )
        return StorageChangeDoc(
            path=target,
            change_id=change_id,
            created_at=created_at,
            fingerprint=fingerprint,
            hostname=self._hostname,
            pid=os.getpid(),
            worker=worker_id,
            payload=payload,
        )

    def merge(self) -> QueueStats:
        """Replay queued documents atomically and archive them."""

        docs = self._load_pending_docs()
        stats = self._build_stats(docs)
        self._log_thresholds(stats)
        if not docs:
            return stats

        latest_payload = docs[-1].payload
        self._write_storage(latest_payload)
        for doc in docs:
            self._archive_doc(doc)
        self._prune_processed()
        logger.info(
            "Merged storage queue",
            extra={
                "storage_state": str(self.storage_file),
                "processed": len(docs),
                "latest_change_id": docs[-1].change_id,
            },
        )
        return stats

    def _default_queue_dir(self) -> Path:
        return self.storage_file.parent / f"{self.storage_file.name}.changes"

    def _next_change_id(self) -> str:
        # Time-based prefix maintains deterministic ordering even across hosts.
        prefix = f"{time.time_ns()}"
        return f"{prefix}-{uuid.uuid4().hex}"

    def _load_pending_docs(self) -> list[StorageChangeDoc]:
        docs: list[StorageChangeDoc] = []
        for path in sorted(self.queue_dir.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Failed to parse storage change",
                    extra={"path": str(path), "error": exc.__class__.__name__},
                )
                continue
            try:
                decoded = base64.b64decode(payload["payload"].encode("ascii"))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to decode storage change payload",
                    extra={"path": str(path), "error": exc.__class__.__name__},
                )
                continue
            docs.append(
                StorageChangeDoc(
                    path=path,
                    change_id=str(payload.get("change_id")),
                    created_at=float(payload.get("created_at", 0.0)),
                    fingerprint=str(payload.get("fingerprint")),
                    hostname=payload.get("hostname"),
                    pid=payload.get("pid"),
                    worker=payload.get("worker"),
                    payload=decoded,
                )
            )
        docs.sort(key=lambda doc: (doc.created_at, doc.change_id))
        return docs

    def _build_stats(self, docs: Sequence[StorageChangeDoc]) -> QueueStats:
        pending = len(docs)
        oldest_age: float | None = None
        newest_change_id: str | None = None
        if docs:
            now = time.time()
            oldest_age = max(0.0, now - min(doc.created_at for doc in docs))
            newest_change_id = docs[-1].change_id
        return QueueStats(
            pending=pending, oldest_age=oldest_age, newest_change_id=newest_change_id
        )

    def _log_thresholds(self, stats: QueueStats) -> None:
        if stats.pending > self.max_entries:
            logger.critical(
                "Storage queue depth exceeded threshold",
                extra={
                    "storage_state": str(self.storage_file),
                    "pending": stats.pending,
                    "max_entries": self.max_entries,
                },
            )
        if (
            stats.oldest_age is not None
            and self.max_age_seconds > 0
            and stats.oldest_age > self.max_age_seconds
        ):
            logger.critical(
                "Storage queue backlog age exceeded threshold",
                extra={
                    "storage_state": str(self.storage_file),
                    "oldest_age_secs": round(stats.oldest_age, 2),
                    "max_age_secs": self.max_age_seconds,
                },
            )

    def _write_storage(self, payload: bytes) -> None:
        target = self.storage_file
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_suffix(target.suffix + ".tmp")
        with temp_path.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(target)

    def _archive_doc(self, doc: StorageChangeDoc) -> None:
        target = self.processed_dir / doc.path.name
        try:
            doc.path.replace(target)
        except (
            FileNotFoundError
        ):  # pragma: no cover - concurrent merge already moved it
            return

    def _prune_processed(self) -> None:
        if self.processed_retention_seconds <= 0:
            return
        threshold = time.time() - self.processed_retention_seconds
        for path in list(self.processed_dir.glob("*.json")):
            try:
                stat = path.stat()
            except OSError:  # pragma: no cover - best effort cleanup
                continue
            if stat.st_mtime < threshold:
                with contextlib.suppress(OSError):
                    path.unlink()


def normalize_payload(payload: str | bytes | dict) -> bytes:
    """Convert mixed payload types to canonical UTF-8 bytes."""

    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


__all__ = [
    "StorageQueue",
    "StorageSnapshot",
    "StorageChangeDoc",
    "QueueStats",
    "capture_snapshot",
    "compute_fingerprint",
    "normalize_payload",
]
