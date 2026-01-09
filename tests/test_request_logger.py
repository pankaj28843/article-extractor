"""Tests for request_logger module."""

from __future__ import annotations

import logging
import time

from article_extractor.request_logger import (
    build_request_context,
    compute_duration_ms,
    log_request_failure,
    log_request_success,
)


class TestBuildRequestContext:
    """Tests for build_request_context helper."""

    def test_builds_complete_context(self):
        context = build_request_context(
            request_id="req-123",
            method="POST",
            path="/extract",
            status_code=200,
            duration_ms=42.5,
            url_hint="https://example.com/page",
        )
        assert context == {
            "request_id": "req-123",
            "method": "POST",
            "path": "/extract",
            "status_code": 200,
            "duration_ms": 42.5,
            "url": "https://example.com/page",
        }

    def test_preserves_all_field_types(self):
        context = build_request_context(
            request_id="abc",
            method="GET",
            path="/",
            status_code=500,
            duration_ms=100.25,
            url_hint="https://test.com",
        )
        assert isinstance(context["request_id"], str)
        assert isinstance(context["method"], str)
        assert isinstance(context["path"], str)
        assert isinstance(context["status_code"], int)
        assert isinstance(context["duration_ms"], float)
        assert isinstance(context["url"], str)


class TestComputeDurationMs:
    """Tests for compute_duration_ms helper."""

    def test_computes_duration_from_start_time(self):
        start = time.perf_counter()
        time.sleep(0.01)
        duration = compute_duration_ms(start)
        assert duration >= 10.0
        assert duration < 50.0

    def test_rounds_to_two_decimal_places(self):
        start = time.perf_counter()
        duration = compute_duration_ms(start)
        assert round(duration, 2) == duration


class TestLogRequestFailure:
    """Tests for log_request_failure function."""

    def test_logs_exception_with_context(self, caplog):
        caplog.set_level(logging.ERROR)
        start = time.perf_counter()

        duration = log_request_failure(
            request_id="fail-123",
            method="POST",
            path="/api/extract",
            url_hint="https://example.com/test",
            start_time=start,
            status_code=500,
        )

        assert duration >= 0
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "ERROR"
        assert record.message == "Request failed"
        assert record.request_id == "fail-123"
        assert record.method == "POST"
        assert record.path == "/api/extract"
        assert record.status_code == 500
        assert record.url == "https://example.com/test"
        assert record.duration_ms == duration

    def test_uses_default_500_status(self, caplog):
        caplog.set_level(logging.ERROR)
        start = time.perf_counter()

        log_request_failure(
            request_id="test",
            method="GET",
            path="/",
            url_hint="https://test.com",
            start_time=start,
        )

        assert caplog.records[0].status_code == 500

    def test_returns_computed_duration(self):
        start = time.perf_counter()
        time.sleep(0.005)

        duration = log_request_failure(
            request_id="test",
            method="GET",
            path="/",
            url_hint="https://test.com",
            start_time=start,
        )

        assert duration >= 5.0


class TestLogRequestSuccess:
    """Tests for log_request_success function."""

    def test_logs_info_with_context(self, caplog):
        caplog.set_level(logging.INFO)
        start = time.perf_counter()

        duration = log_request_success(
            request_id="success-456",
            method="GET",
            path="/health",
            url_hint="https://example.com/api",
            start_time=start,
            status_code=200,
        )

        assert duration >= 0
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelname == "INFO"
        assert record.message == "Request complete"
        assert record.request_id == "success-456"
        assert record.method == "GET"
        assert record.path == "/health"
        assert record.status_code == 200
        assert record.url == "https://example.com/api"
        assert record.duration_ms == duration

    def test_handles_non_200_success_codes(self, caplog):
        caplog.set_level(logging.INFO)
        start = time.perf_counter()

        log_request_success(
            request_id="test",
            method="POST",
            path="/create",
            url_hint="https://test.com",
            start_time=start,
            status_code=201,
        )

        assert caplog.records[0].status_code == 201

    def test_returns_computed_duration(self):
        start = time.perf_counter()
        time.sleep(0.005)

        duration = log_request_success(
            request_id="test",
            method="GET",
            path="/",
            url_hint="https://test.com",
            start_time=start,
            status_code=200,
        )

        assert duration >= 5.0
