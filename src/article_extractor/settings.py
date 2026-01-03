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
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


class ServiceSettings(BaseSettings):
    """Typed configuration shared by the CLI and FastAPI server."""

    cache_size: int = Field(default=1000, ge=1)
    threadpool_size: int | None = Field(default=None)
    prefer_playwright: bool = Field(default=True)
    storage_state_file: Path = Field(default=DEFAULT_STORAGE_PATH)

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
        return _coerce_bool(value, default=True)

    @field_validator("storage_state_file", mode="before")
    @classmethod
    def _expand_storage(cls, value: Any):
        if value in (None, ""):
            return DEFAULT_STORAGE_PATH
        return Path(value).expanduser()

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


def _coerce_bool(value: Any, *, default: bool) -> bool:
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
                PREFER_ENV,
                value,
                default,
            )
    elif isinstance(value, (int, float)):
        result = bool(value)
    elif value in (None, ""):
        result = default
    return result


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
