"""Tests for observability helpers."""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from article_extractor import observability
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


def test_strip_url_returns_original_on_value_error(monkeypatch):
    def _explode(_url):
        raise ValueError("bad url")

    monkeypatch.setattr(observability, "urlsplit", _explode)

    assert strip_url("//invalid") == "//invalid"


def test_strip_url_returns_original_when_missing_scheme():
    assert strip_url("example.com/path") == "example.com/path"


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


def test_build_url_log_context_skips_hash_when_unavailable(monkeypatch):
    monkeypatch.setattr(observability, "stable_url_hash", lambda *_a, **_k: None)

    context = build_url_log_context("https://example.com/path")

    assert context == {"url": "https://example.com/path"}


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


def test_metrics_emitter_disabled_skips_emit():
    with patch.object(MetricsEmitter, "_emit", autospec=True) as emit_mock:
        emitter = MetricsEmitter(component="cli", enabled=False, sink="log")
        emitter.increment("noop")
        emitter.observe("noop", value=1.0)

    emit_mock.assert_not_called()


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


def test_metrics_emitter_statsd_without_client_noops():
    emitter = MetricsEmitter(component="cli", enabled=True, sink="statsd")

    emitter.increment("noop")


def test_json_formatter_includes_custom_fields():
    formatter = observability._JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.component = "cli"
    record.extra_field = "value"

    payload = json.loads(formatter.format(record))

    assert payload["component"] == "cli"
    assert payload["extra_field"] == "value"


def test_json_formatter_includes_stack_info():
    formatter = observability._JsonFormatter()
    record = logging.LogRecord(
        name="stack",
        level=logging.ERROR,
        pathname=__file__,
        lineno=123,
        msg="boom",
        args=(),
        exc_info=None,
    )
    record.component = "cli"
    record.stack_info = "stacktrace"
    try:
        raise RuntimeError("explode")
    except RuntimeError as exc:
        record.exc_info = (exc.__class__, exc, exc.__traceback__)

    payload = json.loads(formatter.format(record))

    assert payload["stack"] == "stacktrace"
    assert "exc_info" in payload


def test_text_formatter_appends_context_fields():
    formatter = observability._TextFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=99,
        msg="Request complete",
        args=(),
        exc_info=None,
    )
    record.component = "server"
    record.request_id = "req-123"
    record.status_code = 200
    record.url = "https://example.com"

    formatted = formatter.format(record)

    assert "server" in formatted
    assert "request_id=req-123" in formatted
    assert "status_code=200" in formatted


def test_text_formatter_appends_exception_info():
    formatter = observability._TextFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=101,
        msg="boom",
        args=(),
        exc_info=None,
    )
    record.component = "cli"
    try:
        raise RuntimeError("explode")
    except RuntimeError as exc:
        record.exc_info = (exc.__class__, exc, exc.__traceback__)

    formatted = formatter.format(record)

    assert "RuntimeError" in formatted


def test_text_formatter_without_extras_returns_base():
    formatter = observability._TextFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=77,
        msg="plain log",
        args=(),
        exc_info=None,
    )
    record.component = "cli"

    formatted = formatter.format(record)

    assert "|" not in formatted


def test_component_filter_sets_component():
    flt = observability._ComponentFilter("fetcher")
    record = logging.LogRecord(
        name="any",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="message",
        args=(),
        exc_info=None,
    )

    assert flt.filter(record) is True
    assert record.component == "fetcher"


def test_statsd_client_send_serializes_namespace_and_tags(monkeypatch):
    sent = {}

    class DummySocket:
        def __init__(self, *_args, **_kwargs):
            sent["created"] = True

        def setblocking(self, _flag):
            return None

        def sendto(self, payload, address):
            sent["payload"] = payload.decode("utf-8")
            sent["address"] = address

    def _socket_factory(*_args, **_kwargs):
        return DummySocket()

    monkeypatch.setattr(observability.socket, "socket", _socket_factory)

    client = observability._StatsdClient("localhost", 8125, namespace="article")
    client.send(
        metric_type="counter",
        metric_name="hits",
        metric_value=2,
        tags={"env": "test"},
    )

    assert sent["payload"] == "article.hits:2|c|#env:test"
    assert sent["address"] == ("localhost", 8125)


def test_statsd_client_send_without_namespace_or_tags(monkeypatch):
    sent = {}

    class DummySocket:
        def setblocking(self, _flag):
            return None

        def sendto(self, payload, address):
            sent["payload"] = payload.decode("utf-8")
            sent["address"] = address

    monkeypatch.setattr(
        observability.socket, "socket", lambda *_args, **_kwargs: DummySocket()
    )

    client = observability._StatsdClient("localhost", 8125, namespace=None)
    client.send(
        metric_type="counter",
        metric_name="hits",
        metric_value=1,
        tags=None,
    )

    assert sent["payload"] == "hits:1|c"
    assert sent["address"] == ("localhost", 8125)


def test_statsd_client_send_skips_empty_serialized_tags(monkeypatch):
    sent = {}

    class DummySocket:
        def setblocking(self, _flag):
            return None

        def sendto(self, payload, address):
            sent["payload"] = payload.decode("utf-8")
            sent["address"] = address

    class _TruthyEmptyTags(dict):
        def __bool__(self):
            return True

    monkeypatch.setattr(
        observability.socket, "socket", lambda *_args, **_kwargs: DummySocket()
    )

    client = observability._StatsdClient("localhost", 8125, namespace=None)
    client.send(
        metric_type="counter",
        metric_name="hits",
        metric_value=1,
        tags=_TruthyEmptyTags(),
    )

    assert sent["payload"] == "hits:1|c"
    assert sent["address"] == ("localhost", 8125)


def test_statsd_client_raises_for_unknown_metric_type(monkeypatch):
    class DummySocket:
        def setblocking(self, _flag):
            return None

        def sendto(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        observability.socket, "socket", lambda *_args, **_kwargs: DummySocket()
    )
    client = observability._StatsdClient("localhost", 8125, namespace=None)

    with pytest.raises(OSError, match="Unsupported StatsD metric type"):
        client.send(
            metric_type="histogram",
            metric_name="demo",
            metric_value=1,
            tags=None,
        )


def test_metrics_emitter_statsd_logs_debug_on_failure():
    fake_client = MagicMock()
    fake_client.send.side_effect = OSError("blocked")
    debug_logger = MagicMock()

    with patch(
        "article_extractor.observability.logging.getLogger", return_value=debug_logger
    ):
        emitter = MetricsEmitter(
            component="cli",
            enabled=True,
            sink="statsd",
            statsd_client=fake_client,
        )
        emitter.increment("fail_metric")

    debug_logger.debug.assert_called_once()


def test_build_metrics_emitter_handles_unsupported_sink(caplog):
    caplog.set_level("WARNING")
    emitter = build_metrics_emitter(component="cli", enabled=True, sink="otlp")

    assert emitter.enabled is False
    assert any("Unsupported metrics sink" in msg for msg in caplog.messages)


def test_build_metrics_emitter_statsd_init_failure(monkeypatch, caplog):
    caplog.set_level("WARNING")

    def _boom(*_args, **_kwargs):
        raise OSError("bad socket")

    monkeypatch.setattr(observability, "_StatsdClient", _boom)

    emitter = build_metrics_emitter(
        component="cli",
        enabled=True,
        sink="statsd",
        statsd_host="localhost",
        statsd_port=8125,
    )

    assert emitter.enabled is False
    assert any("Failed to initialize StatsD sink" in msg for msg in caplog.messages)


def test_format_helpers_normalize_values():
    assert observability._normalize_format("TEXT") == "text"
    assert observability._normalize_format("unknown") == "json"
    assert observability._resolve_level("warning") == logging.WARNING
    assert observability._resolve_level(15) == 15
    assert observability._resolve_level("bogus") is None
    assert observability._resolve_level({}) is None


def test_metrics_emitter_log_sink_copies_tags():
    logger = MagicMock()
    with patch(
        "article_extractor.observability.logging.getLogger",
        return_value=logger,
    ):
        emitter = build_metrics_emitter(component="cli", enabled=True, sink="log")
        emitter.increment("demo", tags={"foo": "bar"})

    logger.info.assert_called_once()
    extra = logger.info.call_args.kwargs["extra"]
    assert extra["metric_tags"] == {"foo": "bar"}


def test_metrics_emitter_log_sink_omits_empty_tags():
    logger = MagicMock()
    with patch(
        "article_extractor.observability.logging.getLogger",
        return_value=logger,
    ):
        emitter = build_metrics_emitter(component="cli", enabled=True, sink="log")
        emitter.increment("demo")

    extra = logger.info.call_args.kwargs["extra"]
    assert "metric_tags" not in extra


def test_metrics_emitter_statsd_sink_handles_timer(monkeypatch):
    client = MagicMock()

    def _client_factory(*_args, **_kwargs):
        return client

    monkeypatch.setattr(observability, "_StatsdClient", _client_factory)

    emitter = build_metrics_emitter(
        component="cli",
        enabled=True,
        sink="statsd",
        statsd_host="localhost",
        statsd_port=8125,
        namespace="article",
    )
    emitter.observe("render_time", value=12.5, tags={"env": "test"})

    client.send.assert_called_once()
    kwargs = client.send.call_args.kwargs
    assert kwargs["metric_type"] == "timer"
    assert kwargs["tags"] == {"env": "test"}


def test_build_metrics_emitter_log_disabled_when_enabled_false():
    emitter = build_metrics_emitter(component="cli", enabled=False)

    assert emitter.enabled is False


def test_stable_url_hash_returns_none_for_invalid():
    assert stable_url_hash(None) is None


def test_component_filter_integration_with_logger(monkeypatch):
    handler = logging.StreamHandler()
    monkeypatch.setattr(
        "article_extractor.observability.logging.StreamHandler",
        lambda: handler,
    )
    mock_basic = MagicMock()
    monkeypatch.setattr(
        "article_extractor.observability.logging.basicConfig", mock_basic
    )

    observability.setup_logging(component="cli", log_format="text", level="info")

    assert handler.filters
    assert isinstance(handler.filters[0], observability._ComponentFilter)
