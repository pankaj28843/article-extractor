"""Network configuration helpers for fetchers and server surfaces."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import urlparse

from .types import NetworkOptions

ENV_STORAGE_KEY = "PLAYWRIGHT_STORAGE_STATE_FILE"
ARTICLE_EXTRACTOR_STORAGE_ENV = "ARTICLE_EXTRACTOR_STORAGE_STATE_FILE"
STORAGE_ENV_KEYS = (ARTICLE_EXTRACTOR_STORAGE_ENV, ENV_STORAGE_KEY)
DEFAULT_STORAGE_PATH = Path.home() / ".article-extractor" / "storage_state.json"
DEFAULT_PROXY_BYPASS = ("localhost", "127.0.0.1", "::1")

__all__ = [
    "DEFAULT_PROXY_BYPASS",
    "DEFAULT_STORAGE_PATH",
    "STORAGE_ENV_KEYS",
    "host_matches_no_proxy",
    "resolve_network_options",
]


def resolve_network_options(
    *,
    url: str | None = None,
    env: Mapping[str, str] | None = None,
    base: NetworkOptions | None = None,
    user_agent: str | None = None,
    randomize_user_agent: bool | None = None,
    proxy: str | None = None,
    proxy_bypass: Sequence[str] | None = None,
    headed: bool | None = None,
    user_interaction_timeout: float | None = None,
    storage_state_path: str | Path | None = None,
) -> NetworkOptions:
    """Merge CLI/server overrides with environment and defaults."""

    env = env or os.environ
    base = base or NetworkOptions()

    resolved_proxy = _coalesce(
        proxy,
        base.proxy,
        _determine_proxy_from_env(url, env),
    )

    resolved_randomize = _coalesce(
        randomize_user_agent,
        base.randomize_user_agent,
        False,
    )

    resolved_headed = _coalesce(headed, base.headed, False)
    resolved_timeout = _coalesce(
        user_interaction_timeout,
        base.user_interaction_timeout,
        0.0,
    )
    resolved_storage = _resolve_storage_state_path(
        storage_state_path,
        base.storage_state_path,
        env,
    )

    bypass_values = list(DEFAULT_PROXY_BYPASS)
    bypass_values.extend(base.proxy_bypass)
    bypass_values.extend(_parse_no_proxy(env))
    if proxy_bypass:
        bypass_values.extend(proxy_bypass)

    return NetworkOptions(
        user_agent=user_agent if user_agent is not None else base.user_agent,
        randomize_user_agent=bool(resolved_randomize),
        proxy=resolved_proxy,
        proxy_bypass=_normalize_bypass(bypass_values),
        headed=bool(resolved_headed),
        user_interaction_timeout=float(resolved_timeout),
        storage_state_path=resolved_storage,
    )


def host_matches_no_proxy(  # noqa: PLR0911 - multiple early returns aid readability
    host: str | None, patterns: Sequence[str]
) -> bool:
    """Return True if host should bypass proxy according to NO_PROXY semantics."""

    if not host:
        return True

    host = host.lower()

    for raw in patterns:
        target = raw.strip().lower()
        if not target:
            continue
        if target == "*":
            return True
        if target.startswith("."):
            if host.endswith(target.lstrip(".")):
                return True
        elif target.startswith("*"):
            suffix = target.lstrip("*")
            if suffix and host.endswith(suffix):
                return True
        elif target.count(":") == 1:
            hostname, _port = target.split(":", 1)
            if hostname and host == hostname:
                return True
        elif host == target:
            return True
    return False


def _resolve_storage_state_path(
    explicit: str | Path | None,
    base: Path | None,
    env: Mapping[str, str],
) -> Path | None:
    if explicit is not None:
        return Path(explicit).expanduser()
    if base is not None:
        return base
    env_value = _lookup_storage_env(env)
    if env_value:
        return Path(env_value).expanduser()
    return None


def _lookup_storage_env(env: Mapping[str, str]) -> str | None:
    for key in STORAGE_ENV_KEYS:
        value = _lookup_env(env, key)
        if value:
            return value
    return None


def _determine_proxy_from_env(url: str | None, env: Mapping[str, str]) -> str | None:
    scheme = None
    if url:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()

    lookup_order: list[str] = []
    if scheme == "https":
        lookup_order.append("HTTPS_PROXY")
    elif scheme == "http":
        lookup_order.append("HTTP_PROXY")
    else:
        lookup_order.extend(["HTTPS_PROXY", "HTTP_PROXY"])
    lookup_order.append("ALL_PROXY")

    for key in lookup_order:
        value = _lookup_env(env, key)
        if value:
            return value
    return None


def _parse_no_proxy(env: Mapping[str, str]) -> list[str]:
    raw = _lookup_env(env, "NO_PROXY")
    if not raw:
        return []
    parts = [part.strip() for part in raw.split(",")]
    return [part for part in parts if part]


def _lookup_env(env: Mapping[str, str], key: str) -> str | None:
    for variant in (key, key.lower()):
        value = env.get(variant)
        if value:
            return value
    return None


def _normalize_bypass(values: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip().lower()
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)
    return tuple(normalized)


def _coalesce(*values):
    for value in values:
        if value is not None:
            return value
    return None
