"""Tests for storage utilities."""

from __future__ import annotations

from pathlib import Path

from article_extractor.storage import main, purge_storage_directory


def test_purge_storage_directory_resets_contents(tmp_path):
    target = tmp_path / "storage"
    target.mkdir()
    old_file = target / "old.txt"
    old_file.write_text("payload", encoding="utf-8")

    result = purge_storage_directory(target)

    assert result == target
    assert target.exists()
    assert not any(target.iterdir())


def test_purge_storage_directory_creates_missing(tmp_path):
    target = tmp_path / "missing"

    result = purge_storage_directory(target)

    assert result == target
    assert target.exists()


def test_storage_main_calls_purge(tmp_path, monkeypatch):
    target = tmp_path / "cli"
    target.mkdir()
    (target / "data.bin").write_text("cache", encoding="utf-8")

    calls: list[Path] = []

    def fake_purge(path: Path) -> Path:
        calls.append(path)
        return path

    monkeypatch.setattr(
        "article_extractor.storage.purge_storage_directory",
        fake_purge,
    )

    assert main([str(target)]) == 0
    assert calls == [target]
