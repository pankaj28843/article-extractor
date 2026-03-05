"""Fixture-driven extraction tests for full page HTML samples."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from justhtml import JustHTML

from article_extractor import extract_article

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "fullpage_to_article_html"


@dataclass(frozen=True)
class FixtureCase:
    host: str
    case: str
    url: str
    raw_path: Path
    expected_path: Path


def _normalized_inner_text(fragment: str) -> str:
    wrapped = f"<div>{fragment}</div>"
    doc = JustHTML(wrapped, safe=False)
    containers = doc.query("div")
    text = containers[0].to_text(separator=" ", strip=True) if containers else fragment
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", text)


def _load_fixture_cases() -> list[FixtureCase]:
    cases: list[FixtureCase] = []
    for meta_path in sorted(FIXTURE_ROOT.glob("*/*/meta.json")):
        case_dir = meta_path.parent
        raw_path = case_dir / "raw.html"
        expected_path = case_dir / "expected.html"
        if not raw_path.exists() or not expected_path.exists():
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        url = str(meta.get("url", "")).strip()
        if not url:
            continue

        cases.append(
            FixtureCase(
                host=case_dir.parent.name,
                case=case_dir.name,
                url=url,
                raw_path=raw_path,
                expected_path=expected_path,
            )
        )
    return cases


FIXTURE_CASES = _load_fixture_cases()


@pytest.mark.integration
def test_fixture_corpus_has_expected_minimum_size():
    """Fixture corpus should include broad host coverage for regression safety."""
    assert FIXTURE_ROOT.exists()
    assert len(FIXTURE_CASES) >= 27


@pytest.mark.integration
@pytest.mark.parametrize(
    "fixture_case",
    FIXTURE_CASES,
    ids=lambda case: f"{case.host}/{case.case}",
)
def test_fullpage_to_article_fixture_corpus(fixture_case: FixtureCase):
    raw_html = fixture_case.raw_path.read_text(encoding="utf-8")
    expected_html = fixture_case.expected_path.read_text(encoding="utf-8")

    result = extract_article(raw_html, url=fixture_case.url)

    assert result.success, (
        f"Extraction failed for fixture {fixture_case.host}/{fixture_case.case} "
        f"({fixture_case.url})"
    )

    actual_text = _normalized_inner_text(result.content)
    expected_text = _normalized_inner_text(expected_html)

    assert actual_text == expected_text, (
        "Extracted text mismatch for fixture "
        f"{fixture_case.host}/{fixture_case.case} ({fixture_case.url})"
    )
