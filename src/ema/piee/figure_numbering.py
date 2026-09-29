"""Renumber the base's figure groups and their references after composition."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.office.run_range import TextSpan, replace_spans, visible_text

CAPTION = re.compile(r"^(Fig\.\s*(?:nr\.\s*)?)(\d+)(?:\s+([a-z])\))?", re.I)
REFERENCE = re.compile(
    r"(figur(?:a|ii|ile|ilor)(?:\s+cu)?(?:\s+numărul)?\s+)(\d+)(?:\s+([a-z])\))?", re.I
)


@dataclass(frozen=True)
class _Caption:
    index: int
    original: str
    suffix: str | None
    number: str
    letter: str | None


def numbered_caption(source: Path, caption: str) -> str:
    """Allocate a unique provisional number; the final pass places it in document order."""
    root = xml(read_parts(source), "word/document.xml")
    numbers = [
        int(match.group(2))
        for paragraph in root.iter(qn("w:p"))
        if (match := CAPTION.match(visible_text(paragraph)))
    ]
    return f"Fig. nr. {max(numbers, default=0) + 1} {caption.removeprefix('Fig. ')}"


def _captions(paragraphs: list[etree._Element]) -> list[_Caption]:
    result: list[_Caption] = []
    group = 0
    letter = 0
    previous: tuple[str, bool] | None = None
    for index, paragraph in enumerate(paragraphs):
        match = CAPTION.match(visible_text(paragraph))
        if match is None:
            continue
        original, suffix = match.group(2, 3)
        if suffix is None or previous != (original, True):
            group += 1
            letter = 0
        result.append(
            _Caption(
                index, original, suffix, str(group), chr(ord("a") + letter) if suffix else None
            )
        )
        letter += 1
        previous = original, suffix is not None
    return result


def renumber_figures(source: Path, output: Path) -> None:
    """Preserve a/b/c grouping and resolve repeated old numbers by their nearest caption."""
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    paragraphs = list(root.iter(qn("w:p")))
    captions = _captions(paragraphs)
    by_index = {item.index: item for item in captions}
    for index, paragraph in enumerate(paragraphs):
        text = visible_text(paragraph)
        if index in by_index:
            item = by_index[index]
            match = CAPTION.match(text)
            assert match is not None
            suffix = f" {item.letter})" if item.letter else ""
            replace_spans(paragraph, (TextSpan(match.start(2), match.end(), item.number + suffix),))
            continue
        spans: list[TextSpan] = []
        for match in REFERENCE.finditer(text):
            candidates = [
                item
                for item in captions
                if item.original == match.group(2)
                and (match.group(3) is None or item.suffix == match.group(3))
            ]
            nearest = min(candidates, key=lambda item: abs(item.index - index), default=None)
            suffix = f" {nearest.letter})" if nearest and match.group(3) else ""
            spans.append(
                TextSpan(
                    match.start(2),
                    match.end(),
                    nearest.number + suffix if nearest else "n.d.",
                    missing=nearest is None,
                )
            )
        replace_spans(paragraph, tuple(spans))
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
