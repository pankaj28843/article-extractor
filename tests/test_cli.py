"""Tests for CLI module."""

import json
from collections.abc import Mapping
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from article_extractor.cli import main
from article_extractor.types import ArticleResult


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
    assert kwargs["user_interaction_timeout"] == 7.5
    assert kwargs["storage_state_path"] == storage_file
    assert isinstance(env_mapping, Mapping)


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
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 130

    captured = capsys.readouterr()
    assert "Interrupted" in captured.err


def test_main_exception(capsys):
    """Test handling general exceptions."""
    with (
        patch("article_extractor.cli.resolve_network_options"),
        patch(
            "article_extractor.cli.extract_article_from_url",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Test error"),
        ),
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 1

    captured = capsys.readouterr()
    assert "Error: Test error" in captured.err


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
