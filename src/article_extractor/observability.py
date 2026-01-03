"""Logging and observability helpers shared across entry points."""

from __future__ import annotations

import json
import logging
import socket
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit, urlunsplit

LOG_LEVEL_ENV = "ARTICLE_EXTRACTOR_LOG_LEVEL"
LOG_FORMAT_ENV = "ARTICLE_EXTRACTOR_LOG_FORMAT"
DEFAULT_LOG_FORMAT = "json"
_VALID_TEXT_FORMATS = {"json", "text"}

_RESERVED_LOG_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "process",
    "processName",
}


def setup_logging(
    *,
    component: str,
    level: str | int | None = None,
    default_level: str = "INFO",
    log_format: str | None = None,
) -> None:
    """Configure root logging with a deterministic formatter."""

    resolved_format = _normalize_format(log_format)
    effective_level = _resolve_level(level)
    if effective_level is None:
        effective_level = _resolve_level(default_level) or logging.INFO

    handler = logging.StreamHandler()
    handler.addFilter(_ComponentFilter(component))
    if resolved_format == "text":
        handler.setFormatter(_TextFormatter())
    else:
        handler.setFormatter(_JsonFormatter())

    logging.basicConfig(level=effective_level, handlers=[handler], force=True)


def strip_url(url: str | None) -> str | None:
    """Return a URL without credentials, query parameters, or fragments."""

    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    # Preserve host + optional port while dropping credentials.
    netloc = parts.hostname or parts.netloc
    if parts.port and parts.hostname:
        netloc = f"{parts.hostname}:{parts.port}"
    if not parts.scheme or not netloc:
        return url
    sanitized_path = parts.path or "/"
    return urlunsplit((parts.scheme, netloc, sanitized_path, "", ""))


def generate_request_id(seed: str | None = None) -> str:
    """Return a deterministic request id if provided, else a random hex."""

    if seed and seed.strip():
        return seed.strip()
    return uuid.uuid4().hex


def stable_url_hash(url: str | None, *, assume_sanitized: bool = False) -> str | None:
    """Return a short, deterministic hash for sanitized URLs."""

    target = url if assume_sanitized else strip_url(url)
    if not target:
        return None
    digest = sha256(target.encode("utf-8", "ignore")).hexdigest()
    return digest[:16]


def build_url_log_context(url: str | None) -> dict[str, str]:
    """Return a mapping with sanitized url + hash for logging extras."""

    sanitized = strip_url(url)
    context: dict[str, str] = {}
    if sanitized:
        context["url"] = sanitized
        hashed = stable_url_hash(sanitized, assume_sanitized=True)
        if hashed:
            context["url_hash"] = hashed
    return context


class _ComponentFilter(logging.Filter):
    def __init__(self, component: str) -> None:
        super().__init__()
        self.component = component

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        record.component = self.component
        return True


class _JsonFormatter(logging.Formatter):
    """Emit JSON lines compatible with Docker logging drivers."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_ATTRS or key.startswith("_"):
                continue
            if key in ("component", "message", "logger"):
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    """Emit human-friendly key/value logs for local debugging."""

    def __init__(self) -> None:
        super().__init__(fmt="%(asctime)s %(levelname)s %(component)s %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = []
        for field in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "url",
            "url_hash",
        ):
            value = getattr(record, field, None)
            if value is not None:
                extras.append(f"{field}={value}")
        if record.exc_info:
            extras.append(self.formatException(record.exc_info))
        if not extras:
            return base
        return f"{base} | {' '.join(extras)}"


def _resolve_level(value: str | int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in logging._nameToLevel:
            return logging._nameToLevel[normalized]
    return None


def _normalize_format(value: str | None) -> str:
    configured = value or DEFAULT_LOG_FORMAT
    normalized = configured.strip().lower()
    if normalized not in _VALID_TEXT_FORMATS:
        return DEFAULT_LOG_FORMAT
    return normalized


class MetricsEmitter:
    """Opt-in metrics emitter supporting logging and StatsD sinks."""

    def __init__(
        self,
        *,
        component: str,
        enabled: bool,
        sink: str = "log",
        statsd_client: _StatsdClient | None = None,
    ) -> None:
        self.component = component
        self.enabled = enabled
        self.sink = sink
        self._logger = logging.getLogger("article_extractor.metrics")
        self._statsd = statsd_client

    def increment(
        self,
        metric: str,
        *,
        value: int = 1,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        if not self.enabled:
            return
        self._emit("counter", metric, value, tags)

    def observe(
        self,
        metric: str,
        *,
        value: float,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        if not self.enabled:
            return
        self._emit("timer", metric, value, tags)

    def _emit(
        self,
        metric_type: str,
        metric_name: str,
        metric_value: float,
        tags: Mapping[str, str] | None,
    ) -> None:
        if self.sink == "log":
            payload: dict[str, Any] = {
                "metric_component": self.component,
                "metric_name": metric_name,
                "metric_type": metric_type,
                "metric_value": metric_value,
                "metric_sink": self.sink,
            }
            if tags:
                payload["metric_tags"] = dict(tags)
            self._logger.info("metric", extra=payload)
            return

        if self.sink == "statsd" and self._statsd is not None:
            try:
                self._statsd.send(
                    metric_type=metric_type,
                    metric_name=metric_name,
                    metric_value=metric_value,
                    tags=tags,
                )
            except OSError:
                logging.getLogger(__name__).debug(
                    "Failed to send StatsD metric", exc_info=True
                )


class _StatsdClient:
    """Minimal UDP client for StatsD/DogStatsD-compatible sinks."""

    _TYPE_MAP = {
        "counter": "c",
        "timer": "ms",
    }

    def __init__(
        self,
        host: str,
        port: int,
        namespace: str | None = None,
    ) -> None:
        self.address = (host, port)
        sanitized = namespace.strip() if namespace else None
        self.namespace = sanitized.rstrip(".") if sanitized else None
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setblocking(False)

    def send(
        self,
        *,
        metric_type: str,
        metric_name: str,
        metric_value: float,
        tags: Mapping[str, str] | None,
    ) -> None:
        type_code = self._TYPE_MAP.get(metric_type)
        if type_code is None:
            raise OSError(f"Unsupported StatsD metric type: {metric_type}")
        name = metric_name
        if self.namespace:
            name = f"{self.namespace}.{metric_name}"
        body = f"{name}:{metric_value}|{type_code}"
        if tags:
            serialized = ",".join(f"{key}:{value}" for key, value in tags.items())
            if serialized:
                body = f"{body}|#{serialized}"
        self._socket.sendto(body.encode("utf-8"), self.address)


def build_metrics_emitter(
    *,
    component: str,
    enabled: bool,
    sink: str | None = None,
    statsd_host: str | None = None,
    statsd_port: int | None = None,
    namespace: str | None = None,
) -> MetricsEmitter:
    """Return a metrics emitter for the given component."""

    logger = logging.getLogger(__name__)
    if not enabled:
        return MetricsEmitter(component=component, enabled=False, sink=sink or "log")

    destination = (sink or "log").lower()
    if destination == "log":
        return MetricsEmitter(component=component, enabled=True, sink="log")

    if destination == "statsd":
        if not statsd_host or not statsd_port:
            logger.warning(
                "StatsD sink requires host and port; disabling metrics emitter"
            )
            return MetricsEmitter(component=component, enabled=False, sink="statsd")
        try:
            client = _StatsdClient(
                statsd_host,
                statsd_port,
                namespace,
            )
        except OSError as exc:
            logger.warning(
                "Failed to initialize StatsD sink (%s:%s): %s",
                statsd_host,
                statsd_port,
                exc,
            )
            return MetricsEmitter(component=component, enabled=False, sink="statsd")
        return MetricsEmitter(
            component=component,
            enabled=True,
            sink="statsd",
            statsd_client=client,
        )

    logger.warning("Unsupported metrics sink '%s', disabling emitter", destination)
    return MetricsEmitter(component=component, enabled=False, sink=destination)


__all__ = [
    "LOG_LEVEL_ENV",
    "LOG_FORMAT_ENV",
    "MetricsEmitter",
    "build_metrics_emitter",
    "build_url_log_context",
    "generate_request_id",
    "setup_logging",
    "stable_url_hash",
    "strip_url",
]
