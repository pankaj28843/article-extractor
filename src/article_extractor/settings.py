"""Centralized settings management for article-extractor surfaces.

These settings are shared by the CLI, FastAPI server, and helper scripts.
They lean on :mod:`pydantic_settings` so `.env` files and environment
variables stay in sync across entry points.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .network import DEFAULT_STORAGE_PATH

logger = logging.getLogger(__name__)

CACHE_ENV = "ARTICLE_EXTRACTOR_CACHE_SIZE"
THREADPOOL_ENV = "ARTICLE_EXTRACTOR_THREADPOOL_SIZE"
PREFER_ENV = "ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT"
ALIAS_STORAGE_ENV = "ARTICLE_EXTRACTOR_STORAGE_STATE_FILE"
LEGACY_STORAGE_ENV = "PLAYWRIGHT_STORAGE_STATE_FILE"
LOG_LEVEL_ENV = "ARTICLE_EXTRACTOR_LOG_LEVEL"
LOG_FORMAT_ENV = "ARTICLE_EXTRACTOR_LOG_FORMAT"
LOG_DIAGNOSTICS_ENV = "ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS"
METRICS_ENABLED_ENV = "ARTICLE_EXTRACTOR_METRICS_ENABLED"
METRICS_SINK_ENV = "ARTICLE_EXTRACTOR_METRICS_SINK"
METRICS_STATSD_HOST_ENV = "ARTICLE_EXTRACTOR_METRICS_STATSD_HOST"
METRICS_STATSD_PORT_ENV = "ARTICLE_EXTRACTOR_METRICS_STATSD_PORT"
METRICS_NAMESPACE_ENV = "ARTICLE_EXTRACTOR_METRICS_NAMESPACE"
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
VALID_LOG_FORMATS = {"json", "text"}
VALID_METRICS_SINKS = {"log", "statsd"}


class ServiceSettings(BaseSettings):
    """Typed configuration shared by the CLI and FastAPI server."""

    cache_size: int = Field(default=1000, ge=1)
    threadpool_size: int | None = Field(default=None)
    prefer_playwright: bool = Field(default=True)
    storage_state_file: Path = Field(default=DEFAULT_STORAGE_PATH)
    log_level: str | None = Field(default=None)
    log_format: str | None = Field(default=None)
    log_diagnostics: bool = Field(default=False)
    metrics_enabled: bool = Field(default=False)
    metrics_sink: str | None = Field(default=None)
    metrics_statsd_host: str | None = Field(default=None)
    metrics_statsd_port: int | None = Field(default=None)
    metrics_namespace: str | None = Field(default=None)

    model_config = SettingsConfigDict(
        env_prefix="ARTICLE_EXTRACTOR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator("cache_size", mode="before")
    @classmethod
    def _coerce_cache_size(cls, value: Any):
        if value in (None, ""):
            return 1000
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            logger.warning("Invalid %s=%s, falling back to %s", CACHE_ENV, value, 1000)
            return 1000
        return 1 if parsed <= 0 else parsed

    @field_validator("threadpool_size", mode="before")
    @classmethod
    def _coerce_threadpool_size(cls, value: Any):
        return _coerce_positive_int(value, THREADPOOL_ENV, fallback=None)

    @field_validator("prefer_playwright", mode="before")
    @classmethod
    def _coerce_prefer_playwright(cls, value: Any):
        return _coerce_bool(value, default=True, env_name=PREFER_ENV)

    @field_validator("storage_state_file", mode="before")
    @classmethod
    def _expand_storage(cls, value: Any):
        if value in (None, ""):
            return DEFAULT_STORAGE_PATH
        return Path(value).expanduser()

    @field_validator("log_level", mode="before")
    @classmethod
    def _coerce_log_level(cls, value: Any):
        return _coerce_log_level(value)

    @field_validator("log_format", mode="before")
    @classmethod
    def _coerce_log_format(cls, value: Any):
        return _coerce_log_format(value)

    @field_validator("log_diagnostics", mode="before")
    @classmethod
    def _coerce_log_diagnostics(cls, value: Any):
        return _coerce_bool(value, default=False, env_name=LOG_DIAGNOSTICS_ENV)

    @field_validator("metrics_enabled", mode="before")
    @classmethod
    def _coerce_metrics_enabled(cls, value: Any):
        return _coerce_bool(value, default=False, env_name=METRICS_ENABLED_ENV)

    @field_validator("metrics_sink", mode="before")
    @classmethod
    def _coerce_metrics_sink(cls, value: Any):
        return _coerce_metrics_sink(value)

    @field_validator("metrics_statsd_host", mode="before")
    @classmethod
    def _coerce_metrics_host(cls, value: Any):
        return _coerce_metrics_host(value)

    @field_validator("metrics_statsd_port", mode="before")
    @classmethod
    def _coerce_metrics_port(cls, value: Any):
        return _coerce_metrics_port(value)

    @field_validator("metrics_namespace", mode="before")
    @classmethod
    def _coerce_metrics_namespace(cls, value: Any):
        return _coerce_metrics_namespace(value)

    def determine_threadpool_size(self) -> int:
        default_workers = max(4, (os.cpu_count() or 1) * 2)
        return self.threadpool_size or default_workers

    def build_network_env(self) -> Mapping[str, str]:
        env = dict(os.environ)
        storage = str(self.storage_state_file)
        env.setdefault(ALIAS_STORAGE_ENV, storage)
        env.setdefault(LEGACY_STORAGE_ENV, storage)
        return MappingProxyType(env)


def _coerce_positive_int(
    value: Any, env_name: str, *, fallback: int | None
) -> int | None:
    if value in (None, ""):
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid %s=%s, falling back to %s",
            env_name,
            value,
            _format_fallback(fallback),
        )
        return fallback
    if parsed <= 0:
        logger.warning(
            "Invalid %s=%s, falling back to %s",
            env_name,
            value,
            _format_fallback(fallback),
        )
        return fallback
    return parsed


def _format_fallback(value: int | None) -> str | int:
    return value if value is not None else "auto"


def _coerce_bool(value: Any, *, default: bool, env_name: str) -> bool:
    if isinstance(value, bool):
        return value
    result = default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in TRUE_VALUES:
            result = True
        elif normalized in FALSE_VALUES:
            result = False
        else:
            logger.warning(
                "Invalid %s=%s, falling back to %s",
                env_name,
                value,
                default,
            )
    elif isinstance(value, (int, float)):
        result = bool(value)
    elif value in (None, ""):
        result = default
    return result


def _coerce_log_level(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in logging._nameToLevel:
            return normalized
    logger.warning(
        "Invalid %s=%s, falling back to None",
        LOG_LEVEL_ENV,
        value,
    )
    return None


def _coerce_log_format(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_LOG_FORMATS:
            return normalized
    logger.warning(
        "Invalid %s=%s, falling back to auto",
        LOG_FORMAT_ENV,
        value,
    )
    return None


def _coerce_metrics_sink(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_METRICS_SINKS:
            return normalized
    logger.warning(
        "Invalid %s=%s, falling back to None",
        METRICS_SINK_ENV,
        value,
    )
    return None


def _coerce_metrics_host(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        sanitized = value.strip()
        if sanitized:
            return sanitized
    logger.warning(
        "Invalid %s=%s, falling back to None",
        METRICS_STATSD_HOST_ENV,
        value,
    )
    return None


def _coerce_metrics_port(value: Any) -> int | None:
    return _coerce_positive_int(value, METRICS_STATSD_PORT_ENV, fallback=None)


def _coerce_metrics_namespace(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        sanitized = value.strip()
        if sanitized:
            return sanitized
    logger.warning(
        "Invalid %s=%s, falling back to None",
        METRICS_NAMESPACE_ENV,
        value,
    )
    return None


_SETTINGS_OVERRIDE: dict[str, Any] | None = None


@lru_cache(maxsize=1)
def _load_settings() -> ServiceSettings:
    if _SETTINGS_OVERRIDE is not None:
        return ServiceSettings(**_SETTINGS_OVERRIDE)
    return ServiceSettings()


def get_settings() -> ServiceSettings:
    """Return the cached :class:`ServiceSettings` instance."""

    return _load_settings()


def reload_settings(**overrides: Any) -> ServiceSettings:
    """Clear the cached settings and rebuild them.

    Args:
        overrides: Optional keyword overrides useful for tests.
    """

    global _SETTINGS_OVERRIDE
    _load_settings.cache_clear()
    _SETTINGS_OVERRIDE = overrides or None
    return _load_settings()


def settings_dependency() -> ServiceSettings:
    """FastAPI dependency helper returning cached settings."""

    return get_settings()


__all__ = [
    "ServiceSettings",
    "get_settings",
    "reload_settings",
    "settings_dependency",
]
