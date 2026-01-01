"""Tests for CLI module."""

import json
from io import StringIO
from unittest.mock import MagicMock, patch

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
    with (
        patch("article_extractor.cli.asyncio.run", return_value=mock_result),
        patch("sys.argv", ["article-extractor", "https://example.com"]),
    ):
        assert main() == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["url"] == "https://example.com"
    assert result["title"] == "Test Article"
    assert result["success"] is True


def test_main_url_markdown_output(mock_result, capsys):
    """Test extracting from URL with markdown output."""
    with patch("article_extractor.cli.asyncio.run", return_value=mock_result):
        with patch(
            "sys.argv", ["article-extractor", "https://example.com", "-o", "markdown"]
        ):
            assert main() == 0

    captured = capsys.readouterr()
    assert "# Test Article" in captured.out
    assert "Article content" in captured.out


def test_main_url_text_output(mock_result, capsys):
    """Test extracting from URL with text output."""
    with patch("article_extractor.cli.asyncio.run", return_value=mock_result):
        with patch(
            "sys.argv", ["article-extractor", "https://example.com", "-o", "text"]
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


def test_main_extraction_failure(failed_result, capsys):
    """Test handling extraction failure."""
    with patch("article_extractor.cli.asyncio.run", return_value=failed_result):
        with patch("sys.argv", ["article-extractor", "https://example.com"]):
            assert main() == 1

    captured = capsys.readouterr()
    assert "Error: Extraction failed" in captured.err


def test_main_extraction_options(mock_result):
    """Test extraction options are applied."""
    with (
        patch("article_extractor.cli.asyncio.run", return_value=mock_result),
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


def test_main_keyboard_interrupt(capsys):
    """Test handling keyboard interrupt."""
    with patch("article_extractor.cli.asyncio.run", side_effect=KeyboardInterrupt):
        with patch("sys.argv", ["article-extractor", "https://example.com"]):
            assert main() == 130

    captured = capsys.readouterr()
    assert "Interrupted" in captured.err


def test_main_exception(capsys):
    """Test handling general exceptions."""
    with patch(
        "article_extractor.cli.asyncio.run", side_effect=RuntimeError("Test error")
    ):
        with patch("sys.argv", ["article-extractor", "https://example.com"]):
            assert main() == 1

    captured = capsys.readouterr()
    assert "Error: Test error" in captured.err


def test_server_mode():
    """Test starting server mode."""
    mock_uvicorn_module = MagicMock()
    mock_run = MagicMock()
    mock_uvicorn_module.run = mock_run

    with patch.dict("sys.modules", {"uvicorn": mock_uvicorn_module}):
        with patch("sys.argv", ["article-extractor", "--server"]):
            assert main() == 0

    assert mock_run.called


def test_server_mode_custom_host_port():
    """Test server mode with custom host and port."""
    mock_uvicorn_module = MagicMock()
    mock_run = MagicMock()
    mock_uvicorn_module.run = mock_run

    with patch.dict("sys.modules", {"uvicorn": mock_uvicorn_module}):
        with patch(
            "sys.argv",
            ["article-extractor", "--server", "--host", "127.0.0.1", "--port", "8000"],
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
        with patch("sys.argv", ["article-extractor", "--server"]):
            assert main() == 1

    captured = capsys.readouterr()
    assert "Server dependencies not installed" in captured.err
