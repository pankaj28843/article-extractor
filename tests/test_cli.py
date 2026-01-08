"""Tests for CLI module."""

import argparse
import asyncio
import json
from collections.abc import Mapping
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from article_extractor.cli import (
    _describe_source,
    _metrics_source_label,
    _print_crawl_progress,
    _prompt_output_dir,
    _run_crawl_command,
    main,
)
from article_extractor.crawler import CrawlProgress
from article_extractor.types import ArticleResult, NetworkOptions


@pytest.fixture
def mock_result():
    """Sample extraction result."""
    return ArticleResult(
        url="https://example.com",
        title="Test Article",
        content="<p>Article content</p>",
        markdown="# Test Article\n\nArticle content",
        excerpt="Article content",
        word_count=2,
        success=True,
        author="John Doe",
    )


@pytest.fixture
def failed_result():
    """Failed extraction result."""
    return ArticleResult(
        url="https://example.com",
        title="",
        content="",
        markdown="",
        excerpt="",
        word_count=0,
        success=False,
        error="Extraction failed",
    )


def test_describe_source_prefers_stdin():
    args = argparse.Namespace(url=None, file=None, stdin=True)
    assert _describe_source(args) == "stdin"


def test_metrics_source_label_includes_stdin():
    args = argparse.Namespace(url=None, file=None, stdin=True)
    assert _metrics_source_label(args) == "stdin"


def test_main_url_json_output(mock_result, capsys):
    """Test extracting from URL with JSON output."""
    sentinel_network = object()
    with (
        patch(
            "article_extractor.cli.resolve_network_options",
            return_value=sentinel_network,
        ),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract,
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 0
    mock_extract.assert_awaited_once()
    assert mock_extract.await_args.kwargs["network"] is sentinel_network

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["url"] == "https://example.com"
    assert result["title"] == "Test Article"
    assert result["success"] is True


def test_main_url_markdown_output(mock_result, capsys):
    """Test extracting from URL with markdown output."""
    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch(
            "sys.argv",
            ["article-extractor", "https://example.com", "-o", "markdown"],
        ),
    ):
        assert main() == 0

    captured = capsys.readouterr()
    assert "# Test Article" in captured.out
    assert "Article content" in captured.out


def test_main_url_text_output(mock_result, capsys):
    """Test extracting from URL with text output."""
    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch(
            "sys.argv",
            ["article-extractor", "https://example.com", "-o", "text"],
        ),
    ):
        assert main() == 0

    captured = capsys.readouterr()
    assert "Title: Test Article" in captured.out
    assert "Author: John Doe" in captured.out
    assert "Words: 2" in captured.out


def test_main_file_input(mock_result, tmp_path, capsys):
    """Test extracting from file."""
    html_file = tmp_path / "test.html"
    html_file.write_text("<html><body><p>Test content</p></body></html>")

    with patch("article_extractor.cli.extract_article", return_value=mock_result):
        with patch("sys.argv", ["article-extractor", "--file", str(html_file)]):
            assert main() == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["success"] is True


def test_main_stdin_input(mock_result, capsys):
    """Test extracting from stdin."""
    html = "<html><body><p>Test content</p></body></html>"

    with patch("article_extractor.cli.extract_article", return_value=mock_result):
        with patch("sys.stdin", StringIO(html)):
            with patch("sys.argv", ["article-extractor"]):
                assert main() == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["success"] is True


def test_main_configures_logging(mock_result):
    """CLI should configure logging with CLI overrides."""

    with (
        patch("article_extractor.cli.setup_logging") as mock_setup,
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch(
            "sys.argv",
            [
                "article-extractor",
                "https://example.com",
                "--log-level",
                "info",
                "--log-format",
                "text",
            ],
        ),
    ):
        assert main() == 0

    kwargs = mock_setup.call_args.kwargs
    assert kwargs["component"] == "cli"
    assert kwargs["default_level"] == "CRITICAL"
    assert kwargs["log_format"] == "text"
    assert kwargs["level"] == "INFO"


def test_main_uses_settings_logging_defaults(mock_result):
    """Settings-provided log preferences should flow into setup_logging."""

    settings = _settings_stub(
        diagnostics=False,
        log_level="WARNING",
        log_format="text",
    )

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.setup_logging") as mock_setup,
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 0

    kwargs = mock_setup.call_args.kwargs
    assert kwargs["level"] == "WARNING"
    assert kwargs["log_format"] == "text"


def test_main_records_metrics_on_success(mock_result):
    settings = _settings_stub(
        diagnostics=False,
        metrics_enabled=True,
        metrics_sink="log",
    )
    emitter = MagicMock()
    emitter.enabled = True

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.build_metrics_emitter", return_value=emitter),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("sys.argv", ["article-extractor", "https://example.com", "-o", "json"]),
    ):
        assert main() == 0

    increment_call = emitter.increment.call_args
    assert increment_call.args[0] == "cli_extractions_total"
    assert increment_call.kwargs["tags"] == {"source": "url", "output": "json"}
    observe_call = emitter.observe.call_args
    assert observe_call.args[0] == "cli_extraction_duration_ms"
    assert observe_call.kwargs["tags"] == {
        "source": "url",
        "output": "json",
        "success": "true",
    }


def test_main_records_metrics_on_failure(failed_result):
    settings = _settings_stub(
        diagnostics=False,
        metrics_enabled=True,
        metrics_sink="log",
    )
    emitter = MagicMock()
    emitter.enabled = True

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.build_metrics_emitter", return_value=emitter),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=failed_result,
        ),
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 1

    failure_call = emitter.increment.call_args
    assert failure_call.args[0] == "cli_extractions_failed_total"
    assert failure_call.kwargs["tags"] == {"source": "url", "output": "json"}


def test_main_extraction_failure(failed_result, capsys):
    """Test handling extraction failure."""
    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=failed_result,
        ),
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 1

    captured = capsys.readouterr()
    assert "Error: Extraction failed" in captured.err


def test_main_extraction_options(mock_result):
    """Test extraction options are applied."""
    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch(
            "sys.argv",
            [
                "article-extractor",
                "https://example.com",
                "--min-words",
                "200",
                "--no-images",
                "--no-code",
            ],
        ),
    ):
        result = main()
        assert result == 0


def test_main_network_flag_passthrough(mock_result, tmp_path):
    """CLI networking flags should be forwarded to resolve_network_options."""

    storage_file = tmp_path / "state.json"

    with (
        patch("article_extractor.cli.resolve_network_options") as mock_network,
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch(
            "sys.argv",
            [
                "article-extractor",
                "https://example.com",
                "--user-agent",
                "Custom/1.0",
                "--random-user-agent",
                "--proxy",
                "http://proxy:9000",
                "--headed",
                "--user-interaction-timeout",
                "7.5",
                "--storage-state",
                str(storage_file),
            ],
        ),
    ):
        assert main() == 0

    kwargs = mock_network.call_args.kwargs
    env_mapping = kwargs.pop("env")
    assert kwargs["user_agent"] == "Custom/1.0"
    assert kwargs["randomize_user_agent"] is True
    assert kwargs["proxy"] == "http://proxy:9000"
    assert kwargs["headed"] is True
    assert kwargs["user_interaction_timeout"] == pytest.approx(7.5)
    assert kwargs["storage_state_path"] == storage_file
    assert isinstance(env_mapping, Mapping)


def test_main_storage_state_disabled_by_default(mock_result):
    """CLI should leave storage persistence disabled unless flag provided."""

    with (
        patch("article_extractor.cli.resolve_network_options") as mock_network,
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ),
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 0

    kwargs = mock_network.call_args.kwargs
    assert kwargs["storage_state_path"] is None


def test_main_prefer_httpx_flag(mock_result):
    """CLI should respect --prefer-httpx when hitting URLs."""

    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract,
        patch(
            "sys.argv",
            ["article-extractor", "https://example.com", "--prefer-httpx"],
        ),
    ):
        assert main() == 0

    assert mock_extract.await_args.kwargs["prefer_playwright"] is False


def _settings_stub(
    *,
    diagnostics: bool,
    log_level: str | None = "INFO",
    log_format: str | None = "json",
    metrics_enabled: bool = False,
    metrics_sink: str | None = None,
    metrics_statsd_host: str | None = None,
    metrics_statsd_port: int | None = None,
    metrics_namespace: str | None = None,
) -> object:
    class _Settings:
        def __init__(self):
            self.log_level = log_level
            self.log_format = log_format
            self.prefer_playwright = True
            self.log_diagnostics = diagnostics
            self.metrics_enabled = metrics_enabled
            self.metrics_sink = metrics_sink
            self.metrics_statsd_host = metrics_statsd_host
            self.metrics_statsd_port = metrics_statsd_port
            self.metrics_namespace = metrics_namespace

        @staticmethod
        def build_network_env():
            return {}

    return _Settings()


def test_prompt_output_dir_reads_user_input(monkeypatch, tmp_path):
    mock_stdin = MagicMock()
    mock_stdin.isatty.return_value = True
    monkeypatch.setattr("sys.stdin", mock_stdin)
    monkeypatch.setattr("builtins.input", lambda: str(tmp_path))

    result = _prompt_output_dir()

    assert result == tmp_path.resolve()


def test_prompt_output_dir_rejects_blank_input(monkeypatch):
    mock_stdin = MagicMock()
    mock_stdin.isatty.return_value = True
    monkeypatch.setattr("sys.stdin", mock_stdin)
    monkeypatch.setattr("builtins.input", lambda: "")

    with pytest.raises(SystemExit) as exc_info:
        _prompt_output_dir()

    assert exc_info.value.code == 1


def test_main_passes_log_diagnostics_flag(mock_result):
    """CLI should forward the diagnostics toggle derived from settings."""

    with (
        patch(
            "article_extractor.cli.get_settings",
            return_value=_settings_stub(diagnostics=True),
        ),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract,
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 0

    assert mock_extract.await_args.kwargs["diagnostic_logging"] is True


def test_main_disables_diagnostics_when_setting_false(mock_result):
    """Diagnostics remain off unless explicitly enabled via settings/env."""

    with (
        patch(
            "article_extractor.cli.get_settings",
            return_value=_settings_stub(diagnostics=False),
        ),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract,
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 0

    assert mock_extract.await_args.kwargs["diagnostic_logging"] is False


def test_main_keyboard_interrupt(capsys):
    """Test handling keyboard interrupt."""
    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            side_effect=KeyboardInterrupt,
        ),
        patch("article_extractor.cli.logger") as mock_logger,
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 130

    captured = capsys.readouterr()
    assert "Interrupted" in captured.err
    mock_logger.warning.assert_called_once()
    warning_kwargs = mock_logger.warning.call_args.kwargs
    assert warning_kwargs["extra"]["url"].endswith("example.com/")


def test_main_exception(capsys):
    """Test handling general exceptions."""
    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Test error"),
        ),
        patch("article_extractor.cli.logger") as mock_logger,
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 1

    captured = capsys.readouterr()
    assert "Error: Test error" in captured.err
    mock_logger.exception.assert_called_once()
    exception_kwargs = mock_logger.exception.call_args.kwargs
    assert exception_kwargs["extra"]["url"].endswith("example.com/")


def test_main_keyboard_interrupt_without_source_hint(capsys):
    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article",
            side_effect=KeyboardInterrupt,
        ),
        patch("article_extractor.cli.logger") as mock_logger,
        patch("sys.stdin", StringIO("<html></html>")),
        patch("sys.argv", ["article-extractor"]),
    ):
        assert main() == 130

    captured = capsys.readouterr()
    assert "Interrupted" in captured.err
    mock_logger.warning.assert_not_called()


def test_main_exception_without_source_hint(capsys):
    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article",
            side_effect=RuntimeError("boom"),
        ),
        patch("article_extractor.cli.logger") as mock_logger,
        patch("sys.stdin", StringIO("<html></html>")),
        patch("sys.argv", ["article-extractor"]),
    ):
        assert main() == 1

    captured = capsys.readouterr()
    assert "Error: boom" in captured.err
    mock_logger.exception.assert_not_called()


def test_main_keyboard_interrupt_logs_source_hint(monkeypatch):
    with (
        patch(
            "article_extractor.cli._describe_source",
            return_value="https://example.com/",
        ),
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            side_effect=KeyboardInterrupt,
        ),
        patch("article_extractor.cli.logger") as mock_logger,
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 130

    mock_logger.warning.assert_called_once()


def test_main_exception_logs_source_hint(monkeypatch):
    with (
        patch(
            "article_extractor.cli._describe_source",
            return_value="https://example.com/",
        ),
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ),
        patch("article_extractor.cli.logger") as mock_logger,
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 1

    mock_logger.exception.assert_called_once()


def test_server_mode():
    """Test starting server mode."""
    mock_uvicorn_module = MagicMock()
    mock_run = MagicMock()
    mock_uvicorn_module.run = mock_run

    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch.dict("sys.modules", {"uvicorn": mock_uvicorn_module}),
        patch("article_extractor.server.configure_network_defaults") as mock_config,
        patch("article_extractor.server.set_prefer_playwright") as mock_prefer,
        patch("sys.argv", ["article-extractor", "--server"]),
    ):
        assert main() == 0

    assert mock_run.called
    mock_config.assert_called_once()
    mock_prefer.assert_called_once_with(True)


def test_server_mode_custom_host_port():
    """Test server mode with custom host and port."""
    mock_uvicorn_module = MagicMock()
    mock_run = MagicMock()
    mock_uvicorn_module.run = mock_run

    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch.dict("sys.modules", {"uvicorn": mock_uvicorn_module}),
        patch("article_extractor.server.configure_network_defaults"),
        patch("article_extractor.server.set_prefer_playwright"),
        patch(
            "sys.argv",
            ["article-extractor", "--server", "--host", "127.0.0.1", "--port", "8000"],
        ),
    ):
        assert main() == 0

    assert mock_run.called


def test_server_mode_missing_dependencies(capsys):
    """Test server mode with missing dependencies."""
    import builtins

    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "uvicorn":
            raise ImportError("No module named 'uvicorn'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with (
            patch("article_extractor.cli.resolve_network_options"),
            patch("sys.argv", ["article-extractor", "--server"]),
        ):
            assert main() == 1

    captured = capsys.readouterr()
    assert "Server dependencies not installed" in captured.err


def test_server_mode_records_metrics_when_enabled():
    settings = _settings_stub(
        diagnostics=False,
        metrics_enabled=True,
        metrics_sink="statsd",
        metrics_statsd_host="localhost",
        metrics_statsd_port=8125,
        metrics_namespace="article",
    )
    emitter = MagicMock()
    emitter.enabled = True
    mock_uvicorn_module = MagicMock()
    mock_uvicorn_module.run = MagicMock()

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.build_metrics_emitter", return_value=emitter),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch.dict("sys.modules", {"uvicorn": mock_uvicorn_module}),
        patch("article_extractor.server.configure_network_defaults"),
        patch("article_extractor.server.set_prefer_playwright"),
        patch(
            "sys.argv",
            [
                "article-extractor",
                "--server",
                "--host",
                "127.0.0.1",
                "--port",
                "4000",
            ],
        ),
    ):
        assert main() == 0

    emitter.increment.assert_any_call(
        "cli_server_start_total",
        tags={"host": "127.0.0.1", "port": "4000"},
    )


# ----------------------------------------------------------------------
# Crawl subcommand tests (Phase 3.3)
# ----------------------------------------------------------------------


def _crawl_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    base = {
        "output_dir": str(tmp_path),
        "seed": ["https://example.com/start"],
        "sitemap": None,
        "allow_prefix": None,
        "deny_prefix": None,
        "max_pages": 5,
        "max_depth": 2,
        "concurrency": 3,
        "workers": 2,
        "rate_limit": 0.1,
        "follow_links": True,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_print_crawl_progress_truncates_url(capsys):
    long_url = "https://example.com/" + "a" * 100
    progress = CrawlProgress(
        url=long_url,
        status="success",
        fetched=5,
        successful=5,
        failed=0,
        skipped=0,
        remaining=0,
    )

    _print_crawl_progress(progress)

    captured = capsys.readouterr()
    assert long_url[:57] in captured.err
    assert captured.err.strip().startswith("✓ [5/5]")


def test_print_crawl_progress_ignores_unknown_object(capsys):
    _print_crawl_progress(object())

    captured = capsys.readouterr()
    assert captured.err == ""


def test_print_crawl_progress_keeps_short_url(capsys):
    url = "https://example.com/short"
    progress = CrawlProgress(
        url=url,
        status="success",
        fetched=1,
        successful=1,
        failed=0,
        skipped=0,
        remaining=0,
    )

    _print_crawl_progress(progress)

    captured = capsys.readouterr()
    assert url in captured.err


def test_crawl_help_works(capsys):
    """Test crawl --help displays help text."""
    with (
        patch("sys.argv", ["article-extractor", "crawl", "--help"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "Crawl multiple pages" in captured.out
    assert "--seed" in captured.out
    assert "--sitemap" in captured.out
    assert "--output-dir" in captured.out


def test_crawl_requires_seed_or_sitemap(capsys, tmp_path):
    """Test crawl fails when no seed or sitemap provided."""
    settings = _settings_stub(diagnostics=False, metrics_enabled=False)

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "sys.argv",
            ["article-extractor", "crawl", "--output-dir", str(tmp_path)],
        ),
    ):
        result = main()

    assert result == 1
    captured = capsys.readouterr()
    assert "At least one --seed or --sitemap is required" in captured.err


def test_crawl_prompts_for_output_dir_when_missing(capsys, tmp_path, monkeypatch):
    """Test crawl prompts interactively when --output-dir not provided."""
    settings = _settings_stub(diagnostics=False, metrics_enabled=False)

    # Mock stdin to provide the output directory
    monkeypatch.setattr("sys.stdin", StringIO(str(tmp_path) + "\n"))

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch("article_extractor.cli._run_crawl_command") as mock_cmd,
        patch(
            "sys.argv",
            ["article-extractor", "crawl", "--seed", "https://example.com/"],
        ),
    ):
        mock_cmd.return_value = 0
        main()

    # Note: since we're mocking _run_crawl_command, we just verify it was called
    mock_cmd.assert_called_once()


def test_crawl_rejects_missing_output_dir_in_non_tty(capsys, monkeypatch):
    """Test crawl fails in non-interactive mode when --output-dir missing."""
    from article_extractor.cli import _prompt_output_dir

    # Simulate non-TTY stdin
    mock_stdin = MagicMock()
    mock_stdin.isatty.return_value = False
    monkeypatch.setattr("sys.stdin", mock_stdin)

    with pytest.raises(SystemExit) as exc_info:
        _prompt_output_dir()

    assert exc_info.value.code == 1


def test_crawl_validates_output_dir_exists(capsys, tmp_path):
    """Test crawl validates output directory path."""
    settings = _settings_stub(diagnostics=False, metrics_enabled=False)
    invalid_path = tmp_path / "nonexistent" / "deep" / "path"

    mock_manifest = MagicMock()
    mock_manifest.total_pages = 1
    mock_manifest.successful = 1
    mock_manifest.failed = 0
    mock_manifest.skipped = 0

    async def mock_run_crawl(*args, **kwargs):
        await asyncio.sleep(0)
        return mock_manifest

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch("article_extractor.crawler.run_crawl", mock_run_crawl),
        patch(
            "sys.argv",
            [
                "article-extractor",
                "crawl",
                "--seed",
                "https://example.com/",
                "--output-dir",
                str(invalid_path),
            ],
        ),
    ):
        result = main()

    # Should succeed because validate_output_dir creates the directory
    assert result == 0


def test_crawl_parses_all_arguments(tmp_path):
    """Test crawl command parses all flags correctly."""
    settings = _settings_stub(diagnostics=False, metrics_enabled=False)

    mock_manifest = MagicMock()
    mock_manifest.total_pages = 2
    mock_manifest.successful = 2
    mock_manifest.failed = 0
    mock_manifest.skipped = 0

    captured_configs = []

    async def mock_run_crawl(config, **kwargs):
        await asyncio.sleep(0)
        captured_configs.append(config)
        return mock_manifest

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch("article_extractor.crawler.run_crawl", mock_run_crawl),
        patch(
            "sys.argv",
            [
                "article-extractor",
                "crawl",
                "--seed",
                "https://example.com/page1",
                "--seed",
                "https://example.com/page2",
                "--sitemap",
                "https://example.com/sitemap.xml",
                "--output-dir",
                str(tmp_path),
                "--allow-prefix",
                "https://example.com/",
                "--deny-prefix",
                "https://example.com/admin",
                "--max-pages",
                "50",
                "--max-depth",
                "5",
                "--concurrency",
                "10",
                "--rate-limit",
                "0.5",
                "--workers",
                "4",
                "--no-follow-links",
            ],
        ),
    ):
        result = main()

    assert result == 0
    assert captured_configs
    captured_config = captured_configs[0]
    assert len(captured_config.seeds) == 2
    assert "https://example.com/page1" in captured_config.seeds
    assert "https://example.com/page2" in captured_config.seeds
    assert len(captured_config.sitemaps) == 1
    assert captured_config.max_pages == 50
    assert captured_config.max_depth == 5
    assert captured_config.concurrency == 10
    assert captured_config.worker_count == 4
    assert captured_config.rate_limit_delay == pytest.approx(0.5)
    assert captured_config.follow_links is False
    assert "https://example.com/" in captured_config.allow_prefixes
    assert "https://example.com/admin" in captured_config.deny_prefixes


def test_crawl_returns_nonzero_on_failures(tmp_path):
    """Test crawl returns non-zero exit code when there are failures."""
    settings = _settings_stub(diagnostics=False, metrics_enabled=False)

    mock_manifest = MagicMock()
    mock_manifest.total_pages = 2
    mock_manifest.successful = 1
    mock_manifest.failed = 1  # One failure
    mock_manifest.skipped = 0

    async def mock_run_crawl(*args, **kwargs):
        await asyncio.sleep(0)
        return mock_manifest

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch("article_extractor.crawler.run_crawl", mock_run_crawl),
        patch(
            "sys.argv",
            [
                "article-extractor",
                "crawl",
                "--seed",
                "https://example.com/",
                "--output-dir",
                str(tmp_path),
            ],
        ),
    ):
        result = main()

    assert result == 1  # Non-zero due to failures


def test_crawl_rejects_invalid_worker_count(tmp_path, capsys):
    """Crawl should reject worker counts below 1."""
    settings = _settings_stub(diagnostics=False, metrics_enabled=False)

    with (
        patch("article_extractor.cli.get_settings", return_value=settings),
        patch("article_extractor.cli.setup_logging"),
        patch("article_extractor.cli.resolve_network_options"),
        patch("article_extractor.crawler.run_crawl"),
        patch(
            "sys.argv",
            [
                "article-extractor",
                "crawl",
                "--seed",
                "https://example.com/",
                "--output-dir",
                str(tmp_path),
                "--workers",
                "0",
            ],
        ),
    ):
        result = main()

    assert result == 1
    captured = capsys.readouterr()
    assert "--workers must be at least 1" in captured.err


@pytest.mark.asyncio
async def test_run_crawl_command_success(monkeypatch, tmp_path, capsys):
    args = _crawl_args(tmp_path)
    sentinel_network = NetworkOptions()

    async def fake_run_crawl(config, *, network=None, on_progress=None):
        await asyncio.sleep(0)
        assert network is sentinel_network
        assert config.worker_count == args.workers
        if on_progress:
            on_progress(
                CrawlProgress(
                    url="https://example.com/deep/path" + "a" * 80,
                    status="success",
                    fetched=1,
                    successful=1,
                    failed=0,
                    skipped=0,
                    remaining=0,
                )
            )
        return SimpleNamespace(total_pages=1, successful=1, failed=0, skipped=0)

    monkeypatch.setattr(
        "article_extractor.crawler.run_crawl",
        fake_run_crawl,
    )

    result = await _run_crawl_command(args, sentinel_network)

    assert result == 0


@pytest.mark.asyncio
async def test_run_crawl_command_prompts_for_output_dir(monkeypatch, tmp_path):
    args = _crawl_args(tmp_path, output_dir=None)

    async def _fake_run_crawl(*_args, **_kwargs):
        manifest = MagicMock()
        manifest.total_pages = 0
        manifest.successful = 0
        manifest.failed = 0
        manifest.skipped = 0
        return manifest

    monkeypatch.setattr("article_extractor.cli._prompt_output_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "article_extractor.crawler.validate_output_dir", lambda *_a, **_k: None
    )
    monkeypatch.setattr("article_extractor.crawler.run_crawl", _fake_run_crawl)

    result = await _run_crawl_command(args, NetworkOptions())

    assert result == 0


@pytest.mark.asyncio
async def test_run_crawl_command_handles_invalid_output_dir(
    monkeypatch, tmp_path, capsys
):
    args = _crawl_args(tmp_path)

    def _boom(*_args, **_kwargs):
        raise ValueError("bad output")

    monkeypatch.setattr("article_extractor.crawler.validate_output_dir", _boom)

    result = await _run_crawl_command(args, NetworkOptions())

    captured = capsys.readouterr()
    assert result == 1
    assert "bad output" in captured.err


@pytest.mark.asyncio
async def test_run_crawl_command_handles_keyboard_interrupt(
    monkeypatch, tmp_path, capsys
):
    args = _crawl_args(tmp_path)

    async def _boom(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("article_extractor.crawler.run_crawl", _boom)

    result = await _run_crawl_command(args, NetworkOptions())

    captured = capsys.readouterr()
    assert result == 130
    assert "Crawl interrupted" in captured.err


def test_cli_module_runs_as_main(monkeypatch):
    import runpy

    monkeypatch.setattr("sys.argv", ["article-extractor", "--help"])

    with pytest.raises(SystemExit):
        runpy.run_module("article_extractor.cli", run_name="__main__")


@pytest.mark.asyncio
async def test_run_crawl_command_handles_exception(monkeypatch, tmp_path, capsys):
    args = _crawl_args(tmp_path)

    async def failing_crawl(*args, **kwargs):
        await asyncio.sleep(0)
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "article_extractor.crawler.run_crawl",
        failing_crawl,
    )
    mock_logger = MagicMock()
    monkeypatch.setattr("article_extractor.cli.logger", mock_logger)

    result = await _run_crawl_command(args, NetworkOptions())

    assert result == 1
    err = capsys.readouterr().err
    assert "Error: boom" in err
    mock_logger.exception.assert_called_once()
