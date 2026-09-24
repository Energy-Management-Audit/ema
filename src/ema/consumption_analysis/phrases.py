"""Auditable phrase patterns and data-only wording choices."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from ema.core.resources import resource_path
from ema.energy_data.calc import trend as calculate_trend

Direction = Literal["growth", "decline", "constant"]
UNSUPPORTED_COMPARISON = re.compile(
    r"\b(?:cea\s+mai|cel\s+mai|un\s+(?:maxim|minim)|"
    r"valoarea\s+(?:minimă|maximă)|mai\s+(?:mare|mică)\s+decât|"
    r"față\s+de|superior|inferior|depășește)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Phrase:
    source_document: str
    paragraph: int
    direction: str
    pattern: str


@lru_cache(maxsize=1)
def phrase_bank() -> tuple[Phrase, ...]:
    path = resource_path("consumption_analysis", "phrases.jsonl")
    return tuple(
        Phrase(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()
    )


def trend_direction(values: list[float | None], decimals: int = 2) -> Direction | None:
    """Translate the shared energy-data result into a phrase-bank direction."""
    if len(values) < 2 or any(value is None for value in values):
        return None
    wording = calculate_trend([value for value in values if value is not None], decimals)
    if wording == "creștere":
        return "growth"
    if wording == "scădere":
        return "decline"
    return "constant"


def largest_share(shares: dict[str, float | None]) -> str | None:
    present = [(name, value) for name, value in shares.items() if value is not None]
    return sorted(present, key=lambda item: (-item[1], item[0]))[0][0] if present else None


def notable_month(values: dict[int, float | None], *, high: bool) -> int | None:
    present = [(month, value) for month, value in values.items() if value is not None]
    if not present:
        return None
    return sorted(present, key=lambda item: ((-1 if high else 1) * item[1], item[0]))[0][0]


def trend_phrase(  # noqa: PLR0913
    scope: Literal["audit", "piee"],
    subject: str,
    direction: Direction,
    figure_number: str,
    year: int | None = None,
    *,
    source_document: str | None = None,
    source_paragraph: int | None = None,
) -> str | None:
    """Use the first applicable authored pattern; never invent causal commentary."""
    for item in phrase_bank():
        if not item.source_document.startswith(scope) or item.direction != direction:
            continue
        if source_document is not None and (
            item.source_document != source_document or item.paragraph != source_paragraph
        ):
            continue
        if subject.casefold() not in item.pattern.casefold():
            continue
        if "{number}" in item.pattern:
            continue
        if UNSUPPORTED_COMPARISON.search(item.pattern):
            continue
        if "{year}" in item.pattern and year is None:
            continue
        return item.pattern.format(figure_number=figure_number, year=year)
    return None
