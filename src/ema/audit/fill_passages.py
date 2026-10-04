"""Narrative facts as whole verbatim passages: cut to the cap, numbered and recorded."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING

from ema.audit.catalogue_types import PASSAGE_FACTS, max_passages, passage_key
from ema.audit.draft_checks import SENTENCE_END
from ema.audit.fill_tools import FillTools
from ema.core.logging import write_event
from ema.core.workspace import Workspace

if TYPE_CHECKING:
    from ema.audit.fill_extract import ExtractedFact

PASSAGE_CHARS = 1_500
PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def split_passage(quote: str) -> tuple[list[str], list[str]]:
    """A passage cut at sentence or paragraph ends into verbatim pieces of PASSAGE_CHARS at most.

    Returns the pieces and the sentences left out because one alone is longer than the cap:
    a sentence is never cut.
    """
    gaps = sorted(
        {
            (match.start(), match.end())
            for pattern in (SENTENCE_END, PARAGRAPH_BREAK)
            for match in pattern.finditer(quote)
        }
    )
    spans: list[tuple[int, int]] = []
    start = 0
    for gap_start, gap_end in gaps:
        if gap_start > start:
            spans.append((start, gap_start))
        start = max(start, gap_end)
    if start < len(quote):
        spans.append((start, len(quote)))
    pieces: list[str] = []
    dropped: list[str] = []
    first: int | None = None
    last = 0
    for span_start, span_end in spans:
        if span_end - span_start > PASSAGE_CHARS:
            if first is not None:
                pieces.append(quote[first:last])
            dropped.append(quote[span_start:span_end])
            first = None
            continue
        if first is not None and span_end - first > PASSAGE_CHARS:
            pieces.append(quote[first:last])
            first = None
        first = span_start if first is None else first
        last = span_end
    if first is not None:
        pieces.append(quote[first:last])
    return [piece.strip() for piece in pieces if piece.strip()], dropped


def record_passages(
    ws: Workspace,
    job: str,
    tools: Mapping[str, FillTools],
    owner: Mapping[str, str],
    passages: Mapping[str, Mapping[str, tuple[tuple[int, int, int], ExtractedFact]]],
) -> dict[str, int]:
    """Number each fact's passages by their place in the dossier, cut to the cap, and record.

    What does not fit, a sentence over the cap or a piece past the fact's passage cap, is logged.
    """
    counts: dict[str, int] = {}
    dropped: list[dict[str, object]] = []
    for key, located in passages.items():
        pieces: list[tuple[str, ExtractedFact]] = []
        for _, fact in sorted(located.values(), key=lambda item: item[0]):
            kept, long = split_passage(fact.quote)
            seen = {piece for piece, _ in pieces}
            pieces.extend((piece, fact) for piece in kept if piece not in seen)
            dropped.extend(
                {"key": key, "reason": "sentence_over_cap", "chars": len(text)} for text in long
            )
        for number, (piece, fact) in enumerate(pieces[: max_passages(key)], 1):
            tools[owner[key]].record_fact(
                {
                    "key": passage_key(key, number),
                    "value": piece,
                    "name": fact.file,
                    "page": fact.page,
                    "quote": piece,
                }
            )
        dropped.extend(
            {"key": key, "reason": "passage_count", "chars": len(piece)}
            for piece, _ in pieces[max_passages(key) :]
        )
        counts[key] = min(len(pieces), max_passages(key))
    if dropped:
        with ws.connect() as db, ws.job_log(db, job) as handle:
            for item in dropped:
                write_event(handle, "passage_dropped", stage="fill", **item)
    return counts


def drop_stale_passages(
    tools: Mapping[str, FillTools],
    owner: Mapping[str, str],
    counts: Mapping[str, int],
    found: set[str],
) -> None:
    """Passages beyond this run's count are a previous dossier's and must not reach a draft."""
    for key in sorted(PASSAGE_FACTS & owner.keys()):
        for number in range(max(2, counts.get(key, 0) + 1), max_passages(key) + 1):
            if passage_key(key, number) in found:
                tools[owner[key]].mark_missing({"key": passage_key(key, number)})
