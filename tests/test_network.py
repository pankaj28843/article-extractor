"""Tests for network configuration helpers."""

from pathlib import Path

from article_extractor.network import (
    _determine_proxy_from_env,
    _normalize_bypass,
    host_matches_no_proxy,
    resolve_network_options,
)
from article_extractor.types import NetworkOptions


def test_resolve_network_options_prefers_cli_over_env(monkeypatch):
    """Explicit CLI proxy should win over environment definitions."""

    monkeypatch.setenv("HTTPS_PROXY", "http://env-proxy:8080")
    options = resolve_network_options(
        url="https://example.com",
        proxy="http://cli-proxy:9000",
        proxy_bypass=["example.local"],
    )

    assert options.proxy == "http://cli-proxy:9000"
    assert "example.local" in options.proxy_bypass
    monkeypatch.delenv("HTTPS_PROXY", raising=False)


def test_resolve_network_options_reads_env_proxy(monkeypatch):
    """HTTPS urls should pick HTTPS_PROXY when no override is provided."""

    monkeypatch.setenv("HTTPS_PROXY", "http://env-only:8080")
    options = resolve_network_options(url="https://example.com")
    assert options.proxy == "http://env-only:8080"
    monkeypatch.delenv("HTTPS_PROXY", raising=False)


def test_resolve_network_options_merges_no_proxy(monkeypatch):
    """NO_PROXY entries should merge with defaults and overrides."""

    monkeypatch.setenv("NO_PROXY", "corp.local,.svc.cluster.local")
    options = resolve_network_options(proxy_bypass=["*.dev.local"])
    bypass_targets = set(options.proxy_bypass)
    assert "corp.local" in bypass_targets
    assert ".svc.cluster.local" in bypass_targets
    assert "*.dev.local" in bypass_targets
    assert "localhost" in bypass_targets
    monkeypatch.delenv("NO_PROXY", raising=False)


def test_resolve_network_options_storage_state_env(monkeypatch, tmp_path):
    """PLAYWRIGHT_STORAGE_STATE_FILE env var should override defaults."""

    storage_file = tmp_path / "state.json"
    monkeypatch.setenv("PLAYWRIGHT_STORAGE_STATE_FILE", str(storage_file))
    options = resolve_network_options()
    assert options.storage_state_path == Path(storage_file)
    monkeypatch.delenv("PLAYWRIGHT_STORAGE_STATE_FILE", raising=False)


def test_storage_state_alias_env(monkeypatch, tmp_path):
    """ARTICLE_EXTRACTOR_STORAGE_STATE_FILE should act as a namespaced alias."""

    alias_file = tmp_path / "alias-state.json"
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", str(alias_file))

    options = resolve_network_options()

    assert options.storage_state_path == Path(alias_file)

    monkeypatch.delenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", raising=False)


def test_storage_state_path_defaults_to_none(monkeypatch):
    for key in (
        "ARTICLE_EXTRACTOR_STORAGE_STATE_FILE",
        "PLAYWRIGHT_STORAGE_STATE_FILE",
    ):
        monkeypatch.delenv(key, raising=False)

    options = resolve_network_options()

    assert options.storage_state_path is None


def test_determine_proxy_uses_http_proxy():
    env = {"HTTP_PROXY": "http://proxy:8080"}

    assert (
        _determine_proxy_from_env("http://example.com/docs", env) == "http://proxy:8080"
    )


def test_normalize_bypass_dedupes_and_skips_blanks():
    assert _normalize_bypass([" example.com ", "", "EXAMPLE.com", " "]) == (
        "example.com",
    )


def test_storage_state_alias_wins_over_legacy_env(monkeypatch, tmp_path):
    """Alias env vars should take precedence over legacy Playwright env names."""

    alias_file = tmp_path / "alias.json"
    legacy_file = tmp_path / "legacy.json"
    monkeypatch.setenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", str(alias_file))
    monkeypatch.setenv("PLAYWRIGHT_STORAGE_STATE_FILE", str(legacy_file))

    options = resolve_network_options()

    assert options.storage_state_path == Path(alias_file)

    monkeypatch.delenv("ARTICLE_EXTRACTOR_STORAGE_STATE_FILE", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_STORAGE_STATE_FILE", raising=False)


def test_host_matches_no_proxy_patterns():
    """host_matches_no_proxy should honor common pattern forms."""

    patterns = ("localhost", ".example.com", "*.svc.cluster.local", "api.internal:8080")
    assert host_matches_no_proxy("localhost", patterns) is True
    assert host_matches_no_proxy("foo.example.com", patterns) is True
    assert host_matches_no_proxy("bar.svc.cluster.local", patterns) is True
    assert host_matches_no_proxy("api.internal", patterns) is True
    assert host_matches_no_proxy("public.example.net", patterns) is False


def test_resolve_network_options_merges_base_defaults(tmp_path):
    """Base NetworkOptions should seed defaults when CLI/env omit overrides."""

    base_storage = tmp_path / "state.json"
    base = NetworkOptions(
        user_agent="Base-UA",
        randomize_user_agent=True,
        proxy="http://base-proxy:8080",
        proxy_bypass=("Example.COM", " localhost "),
        headed=True,
        user_interaction_timeout=3.25,
        storage_state_path=base_storage,
    )

    options = resolve_network_options(base=base)

    assert options.user_agent == "Base-UA"
    assert options.randomize_user_agent is True
    assert options.proxy == "http://base-proxy:8080"
    assert options.headed is True
    assert options.user_interaction_timeout == 3.25
    assert options.storage_state_path == base_storage
    assert options.proxy_bypass.count("example.com") == 1
    assert options.proxy_bypass.count("localhost") == 1


def test_resolve_network_options_cli_storage_overrides(monkeypatch, tmp_path):
    """Explicit storage path should win over base and environment."""

    env_storage = tmp_path / "env-state.json"
    base_storage = tmp_path / "base-state.json"
    cli_storage = tmp_path / "cli-state.json"
    base = NetworkOptions(storage_state_path=base_storage)

    monkeypatch.setenv("PLAYWRIGHT_STORAGE_STATE_FILE", str(env_storage))

    options = resolve_network_options(base=base, storage_state_path=cli_storage)

    assert options.storage_state_path == cli_storage

    monkeypatch.delenv("PLAYWRIGHT_STORAGE_STATE_FILE", raising=False)


def test_resolve_network_options_all_proxy_fallback(monkeypatch):
    """ALL_PROXY should be used when scheme-specific proxies are absent."""

    for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy"):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("ALL_PROXY", "socks5://catch-all:1080")
    options = resolve_network_options(url="ftp://internal.example")

    assert options.proxy == "socks5://catch-all:1080"

    monkeypatch.delenv("ALL_PROXY", raising=False)


def test_resolve_network_options_case_insensitive_env(monkeypatch):
    """Proxy lookup should honor lowercase env variables per curl semantics."""

    monkeypatch.setenv("https_proxy", "http://lowercase:4321")

    options = resolve_network_options(url="https://secure.example.com")

    assert options.proxy == "http://lowercase:4321"

    monkeypatch.delenv("https_proxy", raising=False)


def test_host_matches_no_proxy_wildcard_and_empty_host():
    """Wildcard '*' and empty hosts should always bypass the proxy."""

    assert host_matches_no_proxy(None, ()) is True
    assert host_matches_no_proxy("", []) is True
    assert host_matches_no_proxy("anywhere", ("*",)) is True
    assert host_matches_no_proxy("svc.internal", ("  ", "*.internal")) is True
