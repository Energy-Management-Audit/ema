"""Extracted wording refuses capitalized names outside the terminology allow-list."""

import json
from pathlib import Path

import pytest
from scripts.extract_s7_phrases import _pattern, safe_pattern

from ema.core.resources import resource_path


@pytest.mark.parametrize(
    "text",
    [
        "Conform figurii numărul {figure_number}, consumul în SEN a crescut.",
        "În perioada analizată, consumul a fost {number} MWh.",
        "pentru anul {year} s-au înregistrat {number} tep.",
    ],
)
def test_anonymous_technical_patterns_are_allowed(text: str) -> None:
    assert safe_pattern(text)


@pytest.mark.parametrize(
    "text",
    [
        "Conform figurii numărul {figure_number}, consumul în OrașulExemplu a crescut.",
        "CompaniaExemplu a înregistrat un consum constant.",
    ],
)
def test_unknown_names_are_refused_even_at_sentence_start(text: str) -> None:
    assert not safe_pattern(text)


def test_bundled_patterns_all_pass_anonymization() -> None:
    path: Path = resource_path("consumption_analysis", "phrases.jsonl")
    assert all(
        safe_pattern(json.loads(line)["pattern"])
        for line in path.read_text(encoding="utf-8").splitlines()
    )


def test_anonymization_preserves_numeric_placeholders() -> None:
    assert _pattern("Conform figurii numărul 4.2, pentru anul 2025 consumul este 12,5 MWh.") == (
        "Conform figurii numărul {figure_number}, pentru anul {year} consumul este {number} MWh."
    )
