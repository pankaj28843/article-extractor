"""Tests for observability helpers."""

from unittest.mock import MagicMock, patch

from article_extractor.observability import (
    MetricsEmitter,
    build_metrics_emitter,
    build_url_log_context,
    generate_request_id,
    stable_url_hash,
    strip_url,
)


def test_strip_url_sanitizes_query_and_credentials():
    raw = "https://user:pass@example.com:8443/path?q=secret#section"
    assert strip_url(raw) == "https://example.com:8443/path"


def test_generate_request_id_prefers_existing_value():
    assert generate_request_id(" abc123 ") == "abc123"
    generated = generate_request_id()
    assert isinstance(generated, str)
    assert len(generated) == 32


def test_stable_url_hash_consistent_and_sanitized():
    first = stable_url_hash("https://example.com/path?a=1")
    second = stable_url_hash("https://example.com/path?b=2")
    assert first == second
    assert first is not None


def test_build_url_log_context_includes_hash():
    context = build_url_log_context("https://user:pass@example.com/path?a=1")
    assert context["url"] == "https://example.com/path"
    assert "url_hash" in context

    empty = build_url_log_context(None)
    assert empty == {}


def test_build_metrics_emitter_disabled_when_not_enabled():
    emitter = build_metrics_emitter(component="cli", enabled=False, sink=None)

    assert isinstance(emitter, MetricsEmitter)
    assert emitter.enabled is False


def test_metrics_emitter_logs_when_enabled():
    logger = MagicMock()
    with patch(
        "article_extractor.observability.logging.getLogger", return_value=logger
    ):
        emitter = build_metrics_emitter(component="cli", enabled=True, sink="log")
        emitter.increment("test_counter", tags={"foo": "bar"})
        emitter.observe("test_timer", value=1.0, tags={"foo": "bar"})

    assert emitter.enabled is True
    assert logger.info.call_count == 2
    first_call = logger.info.call_args_list[0]
    assert first_call.args[0] == "metric"
    assert first_call.kwargs["extra"]["metric_name"] == "test_counter"


def test_metrics_emitter_statsd_sink_sends_metrics():
    fake_client = MagicMock()
    with patch(
        "article_extractor.observability._StatsdClient", return_value=fake_client
    ):
        emitter = build_metrics_emitter(
            component="cli",
            enabled=True,
            sink="statsd",
            statsd_host="127.0.0.1",
            statsd_port=8125,
            namespace="article",
        )
        emitter.increment("test_counter", tags={"foo": "bar"})
        emitter.observe("test_timer", value=12.3, tags={"foo": "bar"})

    assert emitter.enabled is True
    assert fake_client.send.call_count == 2


def test_metrics_emitter_statsd_missing_host_disables(caplog):
    caplog.set_level("WARNING")
    emitter = build_metrics_emitter(
        component="cli",
        enabled=True,
        sink="statsd",
        statsd_host=None,
        statsd_port=8125,
    )

    assert emitter.enabled is False
    assert any("StatsD sink requires host" in message for message in caplog.messages)
