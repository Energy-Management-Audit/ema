"""#163 D3: a ch. 2-3 draft scored against its reference audit and the auditor's final.

The draft keeps the reference's structure, so its ch. 2-3 sections and their order equal the
reference's. The auditor's final, written without Ema, is the bar for length: each section the
draft and the final share has its own text (prose, captions aside) within ±25 % of the final's
words. The draft's other sections and the final's sections the draft lacks are listed only.
All three documents go through the same heading mapper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document

from ema.audit.headings import headings, map_headings

TOLERANCE = 0.25
_CAPTION = re.compile(r"^\s*(?:Tabel|Fig)")


@dataclass(frozen=True)
class SectionScore:
    section: str
    draft_words: int
    # None: her final has no such section, so the length is listed, not scored.
    final_words: int | None

    @property
    def ratio(self) -> float | None:
        return self.draft_words / self.final_words if self.final_words else None

    @property
    def within(self) -> bool:
        if self.final_words is None:
            return True
        if self.ratio is None:
            return self.draft_words == 0
        return 1 - TOLERANCE <= self.ratio <= 1 + TOLERANCE


@dataclass(frozen=True)
class Baseline:
    draft_order: tuple[str, ...]
    reference_order: tuple[str, ...]
    sections: tuple[SectionScore, ...]
    absent: tuple[str, ...]

    @property
    def structure_kept(self) -> bool:
        return bool(self.draft_order) and self.draft_order == self.reference_order

    @property
    def passed(self) -> bool:
        return self.structure_kept and all(item.within for item in self.sections)

    def report(self) -> str:
        lines = [
            f"structure {'kept' if self.structure_kept else 'CHANGED'}",
            f"  draft:     {' '.join(self.draft_order)}",
            f"  reference: {' '.join(self.reference_order)}",
        ]
        for item in self.sections:
            if item.final_words is None:
                lines.append(f"{item.section}: words {item.draft_words}, not in her final")
                continue
            ratio = f"{item.ratio:.2f}" if item.ratio is not None else "-"
            lines.append(
                f"{item.section}: words {item.draft_words}/{item.final_words}, ratio {ratio}"
                + ("" if item.within else " OUT")
            )
        lines.extend(f"{section}: in her final, not in the draft" for section in self.absent)
        return "\n".join(lines)


def outline(path: Path) -> dict[str, int]:
    """The ch. 2-3 sections in order of first appearance, each with its own words summed over
    every heading that maps to it (a 3.1.x process unit is one of several)."""
    paragraphs = Document(str(path)).paragraphs
    starts = sorted(item.index for item in headings(path))
    words: dict[str, int] = {}
    for item in map_headings(path, "audit-01").mapped:
        if not item.section_id.startswith(("ch2", "ch3")):
            continue
        begin = item.heading.index
        end = next((index for index in starts if index > begin), len(paragraphs))
        words[item.section_id] = words.get(item.section_id, 0) + sum(
            len(paragraph.text.split())
            for paragraph in paragraphs[begin + 1 : end]
            if not _CAPTION.match(paragraph.text)
        )
    return words


def score(draft: Path, reference: Path, final: Path) -> Baseline:
    produced, delivered = outline(draft), outline(final)
    return Baseline(
        tuple(produced),
        tuple(outline(reference)),
        tuple(
            SectionScore(section, words, delivered.get(section))
            for section, words in produced.items()
        ),
        tuple(section for section in delivered if section not in produced),
    )
