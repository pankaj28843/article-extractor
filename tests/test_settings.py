"""Tests for centralized ServiceSettings."""

from __future__ import annotations

import pytest

from article_extractor.settings import (
    ServiceSettings,
    _coerce_bool,
    _coerce_log_format,
    _coerce_log_level,
    _coerce_metrics_host,
    _coerce_metrics_namespace,
    _coerce_metrics_sink,
    _coerce_non_negative_float,
    get_settings,
    reload_settings,
    settings_dependency,
)


def test_settings_respect_env_overrides(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_CACHE_SIZE", "2048")
    reload_settings()

    settings = get_settings()

    assert settings.cache_size == 2048

    monkeypatch.delenv("ARTICLE_EXTRACTOR_CACHE_SIZE", raising=False)
    reload_settings()


def test_settings_cache_size_minimum(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_CACHE_SIZE", "0")
    reload_settings()

    assert get_settings().cache_size == 1

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


def test_build_network_env_skips_storage_when_unset(monkeypatch):
    monkeypatch.delenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_STORAGE_STATE_FILE", raising=False)
    reload_settings(storage_state_file=None)

    env_mapping = get_settings().build_network_env()

    assert "ARTICLE_EXTRACTOR_STORAGE_STATE_FILE" not in env_mapping
    assert "PLAYWRIGHT_STORAGE_STATE_FILE" not in env_mapping

    reload_settings()


def test_storage_state_env_defaults_when_blank(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", "")
    reload_settings()

    assert get_settings().storage_state_file is None

    monkeypatch.delenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", raising=False)
    reload_settings()


def test_storage_state_env_sets_path(monkeypatch, tmp_path):
    storage_file = tmp_path / "env-state.json"
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", str(storage_file))
    reload_settings()

    assert get_settings().storage_state_file == storage_file

    monkeypatch.delenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", raising=False)
    reload_settings()


def test_reload_settings_overrides_take_precedence():
    reload_settings(cache_size=321)

    assert get_settings().cache_size == 321

    reload_settings()


def test_settings_log_level_env(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_LOG_LEVEL", "debug")
    reload_settings()

    assert get_settings().log_level == "DEBUG"

    monkeypatch.delenv("ARTICLE_EXTRACTOR_LOG_LEVEL", raising=False)
    reload_settings()


def test_settings_log_format_env(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_LOG_FORMAT", "text")
    reload_settings()

    assert get_settings().log_format == "text"

    monkeypatch.delenv("ARTICLE_EXTRACTOR_LOG_FORMAT", raising=False)
    reload_settings()


def test_settings_log_format_invalid_value_warns(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_LOG_FORMAT", "xml")
    caplog.set_level("WARNING")
    reload_settings()

    assert get_settings().log_format is None
    assert any("Invalid ARTICLE_EXTRACTOR_LOG_FORMAT" in msg for msg in caplog.messages)

    monkeypatch.delenv("ARTICLE_EXTRACTOR_LOG_FORMAT", raising=False)
    reload_settings()


def test_settings_log_diagnostics_env(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS", "1")
    reload_settings()

    assert get_settings().log_diagnostics is True

    monkeypatch.delenv("ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS", raising=False)
    reload_settings()


def test_settings_metrics_enabled_env(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_METRICS_ENABLED", "true")
    reload_settings()

    assert get_settings().metrics_enabled is True

    monkeypatch.delenv("ARTICLE_EXTRACTOR_METRICS_ENABLED", raising=False)
    reload_settings()


def test_settings_metrics_sink_env(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_METRICS_SINK", "log")
    reload_settings()

    assert get_settings().metrics_sink == "log"

    monkeypatch.setenv("ARTICLE_EXTRACTOR_METRICS_SINK", "unsupported")
    reload_settings()

    assert get_settings().metrics_sink is None

    monkeypatch.delenv("ARTICLE_EXTRACTOR_METRICS_SINK", raising=False)
    reload_settings()


def test_settings_metrics_statsd_env(monkeypatch):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_METRICS_STATSD_HOST", "statsd.internal")
    monkeypatch.setenv("ARTICLE_EXTRACTOR_METRICS_STATSD_PORT", "8125")
    monkeypatch.setenv("ARTICLE_EXTRACTOR_METRICS_NAMESPACE", "article")
    reload_settings()

    settings = get_settings()
    assert settings.metrics_statsd_host == "statsd.internal"
    assert settings.metrics_statsd_port == 8125
    assert settings.metrics_namespace == "article"

    monkeypatch.delenv("ARTICLE_EXTRACTOR_METRICS_STATSD_HOST", raising=False)
    monkeypatch.delenv("ARTICLE_EXTRACTOR_METRICS_STATSD_PORT", raising=False)
    monkeypatch.delenv("ARTICLE_EXTRACTOR_METRICS_NAMESPACE", raising=False)
    reload_settings()


def test_settings_prefer_playwright_invalid_value_warns(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", "maybe")
    caplog.set_level("WARNING")
    reload_settings()

    assert get_settings().prefer_playwright is True
    assert any(
        "Invalid ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT" in message
        for message in caplog.messages
    )

    monkeypatch.delenv("ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT", raising=False)
    reload_settings()


def test_settings_log_level_invalid_value_warns(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_LOG_LEVEL", "verbose")
    caplog.set_level("WARNING")
    reload_settings()

    assert get_settings().log_level is None
    assert any("Invalid ARTICLE_EXTRACTOR_LOG_LEVEL" in msg for msg in caplog.messages)

    monkeypatch.delenv("ARTICLE_EXTRACTOR_LOG_LEVEL", raising=False)
    reload_settings()


def test_settings_metrics_host_blank_warns(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_METRICS_STATSD_HOST", "   ")
    caplog.set_level("WARNING")
    reload_settings()

    assert get_settings().metrics_statsd_host is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_METRICS_STATSD_HOST" in msg
        for msg in caplog.messages
    )

    monkeypatch.delenv("ARTICLE_EXTRACTOR_METRICS_STATSD_HOST", raising=False)
    reload_settings()


def test_settings_metrics_namespace_blank_warns(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_METRICS_NAMESPACE", "   ")
    caplog.set_level("WARNING")
    reload_settings()

    assert get_settings().metrics_namespace is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_METRICS_NAMESPACE" in msg for msg in caplog.messages
    )

    monkeypatch.delenv("ARTICLE_EXTRACTOR_METRICS_NAMESPACE", raising=False)
    reload_settings()


def test_storage_queue_env_overrides(tmp_path, monkeypatch):
    queue_dir = tmp_path / "queue"
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_QUEUE_DIR", str(queue_dir))
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_ENTRIES", "42")
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_AGE_SECONDS", "90.5")
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_QUEUE_RETENTION_SECONDS", "12")
    reload_settings()

    settings = get_settings()
    assert settings.storage_queue_dir == queue_dir
    assert settings.storage_queue_max_entries == 42
    assert settings.storage_queue_max_age_seconds == pytest.approx(90.5)
    assert settings.storage_queue_retention_seconds == pytest.approx(12.0)

    for env in [
        "ARTICLE_EXTRACTOR_STORAGE_QUEUE_DIR",
        "ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_ENTRIES",
        "ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_AGE_SECONDS",
        "ARTICLE_EXTRACTOR_STORAGE_QUEUE_RETENTION_SECONDS",
    ]:
        monkeypatch.delenv(env, raising=False)
    reload_settings()


def test_storage_queue_invalid_values_warn(monkeypatch, caplog):
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_ENTRIES", "-5")
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_AGE_SECONDS", "-1")
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_QUEUE_RETENTION_SECONDS", "bad")
    caplog.set_level("WARNING")
    reload_settings()

    settings = get_settings()
    assert settings.storage_queue_max_entries == 20
    assert settings.storage_queue_max_age_seconds == pytest.approx(60.0)
    assert settings.storage_queue_retention_seconds == pytest.approx(300.0)
    assert any(
        "ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_ENTRIES" in message
        for message in caplog.messages
    )

    for env in [
        "ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_ENTRIES",
        "ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_AGE_SECONDS",
        "ARTICLE_EXTRACTOR_STORAGE_QUEUE_RETENTION_SECONDS",
    ]:
        monkeypatch.delenv(env, raising=False)
    reload_settings()


def test_coerce_bool_handles_numeric_values():
    assert _coerce_bool(0, default=True, env_name="TEST") is False
    assert _coerce_bool(2, default=False, env_name="TEST") is True


def test_coerce_cache_size_handles_empty():
    assert ServiceSettings._coerce_cache_size(None) == 1000
    assert ServiceSettings._coerce_cache_size("") == 1000


def test_coerce_non_negative_float_handles_empty():
    assert _coerce_non_negative_float(None, "TEST", fallback=1.5) == 1.5


def test_coerce_bool_handles_empty():
    assert _coerce_bool(None, default=False, env_name="TEST") is False


def test_coerce_bool_handles_empty_string():
    assert _coerce_bool("", default=True, env_name="TEST") is True


def test_coerce_bool_handles_unknown_type():
    assert _coerce_bool(object(), default=True, env_name="TEST") is True


def test_coerce_log_level_invalid_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_log_level("nope") is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_LOG_LEVEL" in message for message in caplog.messages
    )


def test_coerce_log_level_valid():
    assert _coerce_log_level("info") == "INFO"


def test_coerce_log_level_non_string_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_log_level(123) is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_LOG_LEVEL" in message for message in caplog.messages
    )


def test_coerce_log_format_invalid_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_log_format("yaml") is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_LOG_FORMAT" in message for message in caplog.messages
    )


def test_coerce_log_format_valid():
    assert _coerce_log_format("json") == "json"


def test_coerce_log_format_non_string_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_log_format(123) is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_LOG_FORMAT" in message for message in caplog.messages
    )


def test_coerce_metrics_sink_invalid_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_metrics_sink("otlp") is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_METRICS_SINK" in message
        for message in caplog.messages
    )


def test_coerce_metrics_sink_valid():
    assert _coerce_metrics_sink("statsd") == "statsd"


def test_coerce_metrics_sink_non_string_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_metrics_sink(123) is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_METRICS_SINK" in message
        for message in caplog.messages
    )


def test_coerce_metrics_host_invalid_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_metrics_host("   ") is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_METRICS_STATSD_HOST" in message
        for message in caplog.messages
    )


def test_coerce_metrics_host_valid():
    assert _coerce_metrics_host("statsd.local") == "statsd.local"


def test_coerce_metrics_host_non_string_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_metrics_host(123) is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_METRICS_STATSD_HOST" in message
        for message in caplog.messages
    )


def test_coerce_metrics_namespace_invalid_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_metrics_namespace("   ") is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_METRICS_NAMESPACE" in message
        for message in caplog.messages
    )


def test_coerce_metrics_namespace_valid():
    assert _coerce_metrics_namespace("article") == "article"


def test_coerce_metrics_namespace_non_string_warns(caplog):
    caplog.set_level("WARNING")

    assert _coerce_metrics_namespace(123) is None
    assert any(
        "Invalid ARTICLE_EXTRACTOR_METRICS_NAMESPACE" in message
        for message in caplog.messages
    )


def test_settings_dependency_returns_cached_instance():
    reload_settings(cache_size=123)

    try:
        cached = get_settings()
        assert settings_dependency() is cached
        assert settings_dependency().cache_size == 123
    finally:
        reload_settings()
