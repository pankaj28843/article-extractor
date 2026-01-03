"""Tests for centralized ServiceSettings."""

from __future__ import annotations

from article_extractor.settings import get_settings, reload_settings


def test_settings_respect_env_overrides(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_CACHE_SIZE", "2048")
    reload_settings()

    settings = get_settings()

    assert settings.cache_size == 2048

    monkeypatch.delenv("ARTICLE_EXTRACTOR_CACHE_SIZE", raising=False)
    reload_settings()


def test_settings_warn_on_invalid_threadpool(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", "bogus")
    caplog.set_level("WARNING")
    reload_settings()

    settings = get_settings()

    assert settings.threadpool_size is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_THREADPOOL_SIZE" in message
        for message in caplog.messages
    )

    monkeypatch.delenv("ARTICLE_EXTRACTOR_THREADPOOL_SIZE", raising=False)
    reload_settings()


def test_build_network_env_sets_storage_alias(tmp_path):
    storage_file = tmp_path / "storage.json"
    reload_settings(storage_state_file=storage_file)

    env_mapping = get_settings().build_network_env()

    assert env_mapping["ARTICLE_EXTRACTOR_STORAGE_STATE_FILE"] == str(storage_file)
    assert env_mapping["PLAYWRIGHT_STORAGE_STATE_FILE"] == str(storage_file)

    reload_settings()


def test_reload_settings_overrides_take_precedence():
    reload_settings(cache_size=321)

    assert get_settings().cache_size == 321

    reload_settings()
