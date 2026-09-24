"""Versioned offsets for short-year and table-number replacements."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from docx.oxml.ns import qn

from ema.core.office.anchors import AnchorLedger, find
from ema.core.office.base_map import BaseMap
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.office.run_range import TextSpan, replace_spans, visible_text
from ema.piee.dataset import PieeData

PREVIOUS_YEAR = (36, 90, 125, 171, 208)
TABLE_NUMBERS = {219: "fuel", 274: "equivalent", 275: "equivalent"}


@dataclass(frozen=True)
class BodySpan:
    slot: str
    start: int
    end: int
    key: str


def build_body_spans(parts: dict[str, bytes], mapping: BaseMap, output: Path) -> None:
    body = xml(parts, "word/document.xml").find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE base has no body")
    slots = {entry.selector: entry.slot for entry in mapping.elements if entry.kind == "paragraph"}
    spans: list[BodySpan] = []
    for index in (*PREVIOUS_YEAR, *TABLE_NUMBERS):
        paragraph = list(body)[index - 1]
        slot = slots.get(paragraph.getroottree().getelementpath(paragraph))
        if slot is None:
            raise ValueError(f"body paragraph {index} lacks bookmark")
        content = visible_text(paragraph)
        pattern = r"\b20\d{1,2}\b" if index in PREVIOUS_YEAR else r"\b\d+\b"
        matches = list(re.finditer(pattern, content))
        if len(matches) != 1:
            raise ValueError(f"body paragraph {index} has ambiguous replacement")
        match = matches[0]
        key = "previous_year" if index in PREVIOUS_YEAR else TABLE_NUMBERS[index]
        spans.append(BodySpan(slot, match.start(), match.end(), key))
    output.write_text(json.dumps([asdict(item) for item in spans]), encoding="utf-8")


def build_unsourced_slots(parts: dict[str, bytes], mapping: BaseMap, output: Path) -> None:
    body = xml(parts, "word/document.xml").find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE base has no body")
    paragraph = list(body)[404]
    path = paragraph.getroottree().getelementpath(paragraph)
    slots = {entry.selector: entry.slot for entry in mapping.elements if entry.kind == "paragraph"}
    slot = slots.get(path)
    if slot is None:
        raise ValueError("base-specific boiler recommendation lacks bookmark")
    output.write_text(json.dumps([slot]), encoding="utf-8")


def render_body_spans(
    source: Path,
    manifest: Path,
    data: PieeData,
    output: Path,
    ledger: AnchorLedger,
    *,
    water_missing: bool,
) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    for raw in json.loads(manifest.read_text(encoding="utf-8")):
        item = BodySpan(**raw)
        paragraph = find([root], item.slot)
        replacement = (
            str(data.year - 1)
            if item.key == "previous_year"
            else "5"
            if item.key == "fuel"
            else "6"
            if water_missing
            else "8"
        )
        replace_spans(paragraph, (TextSpan(item.start, item.end, replacement),))
        if item.key == "fuel":
            introduction = find([root], "body_218")
            match = re.search(r"(?<=tabelul numărul )\d+", visible_text(introduction))
            if match is None:
                raise ValueError("fuel table reference has no number")
            replace_spans(introduction, (TextSpan(match.start(), match.end(), replacement),))
            ledger.record("body_218")
        if item.key == "previous_year":
            content = visible_text(paragraph)
            if not content.rstrip().endswith("."):
                last = list(paragraph.iter(qn("w:t")))[-1]
                last.text = (last.text or "") + "."
        ledger.record(item.slot)
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
