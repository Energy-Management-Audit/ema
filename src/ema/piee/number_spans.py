"""Local base-version offsets for annual values, rendered through bookmarks."""

# pyright: reportPrivateUsage=false

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
from ema.piee.chart_plan import BINDINGS, chart_series
from ema.piee.dataset import PieeData
from ema.piee.number import prototype_number

GROUPS: tuple[tuple[tuple[int, int, int], str, int], ...] = (
    ((60, 61, 62), "production", 2),
    ((114, 115, 116), "electricity_grid", 2),
    ((148, 149, 150), "electricity_pv", 2),
    ((195, 196, 197), "natural_gas", 2),
    ((232, 233, 234), "fuel", 2),
    ((304, 305, 306), "specific_grid", 4),
    ((316, 317, 318), "specific_gas", 4),
    ((327, 328, 329), "specific_fuel", 4),
    ((338, 339, 340), "specific_total", 4),
)
YEAR_PARAGRAPHS = (
    26,
    31,
    41,
    84,
    85,
    89,
    94,
    95,
    99,
    119,
    120,
    129,
    154,
    157,
    160,
    166,
    170,
    175,
    176,
    180,
    202,
    203,
    207,
    212,
    213,
    217,
)
CHARTS = {
    "production": 4,
    "electricity_grid": 8,
    "electricity_pv": 12,
    "natural_gas": 16,
    "fuel": 20,
    "specific_grid": 25,
    "specific_gas": 26,
    "specific_fuel": 27,
    "specific_total": 28,
}


@dataclass(frozen=True)
class NumberSpan:
    slot: str
    year_start: int
    year_end: int
    value_start: int
    value_end: int
    key: str
    year_offset: int
    decimals: int


@dataclass(frozen=True)
class YearSpan:
    slot: str
    start: int
    end: int
    offset: int


def build_number_spans(parts: dict[str, bytes], mapping: BaseMap, output: Path) -> None:
    root = xml(parts, "word/document.xml")
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE base has no body")
    slots = {entry.selector: entry.slot for entry in mapping.elements if entry.kind == "paragraph"}
    spans: list[NumberSpan] = []
    for indices, key, decimals in GROUPS:
        for offset, index in enumerate(indices):
            paragraph = list(body)[index - 1]
            path = paragraph.getroottree().getelementpath(paragraph)
            slot = slots.get(path)
            if slot is None:
                raise ValueError(f"annual value paragraph {index} lacks a bookmark")
            text = visible_text(paragraph)
            numbers = list(re.finditer(r"\d[\d.,]*", text))
            if len(numbers) != 2 or not re.fullmatch(r"20\d{2}", numbers[0].group()):
                raise ValueError(f"annual value paragraph {index} changed")
            unit = re.search(r"\s+(?:tone/an|MWh/an|tep/tone)\b", text[numbers[1].end() :], re.I)
            if unit is None:
                raise ValueError(f"annual value unit {index} changed")
            spans.append(
                NumberSpan(
                    slot,
                    numbers[0].start(),
                    numbers[0].end(),
                    numbers[1].start(),
                    numbers[1].end() + unit.end(),
                    key,
                    offset - 2,
                    decimals,
                )
            )
    output.write_text(json.dumps([asdict(item) for item in spans]), encoding="utf-8")


def build_year_spans(parts: dict[str, bytes], mapping: BaseMap, output: Path) -> None:
    root = xml(parts, "word/document.xml")
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE base has no body")
    slots = {entry.selector: entry.slot for entry in mapping.elements if entry.kind == "paragraph"}
    spans: list[YearSpan] = []
    for index in YEAR_PARAGRAPHS:
        paragraph = list(body)[index - 1]
        slot = slots.get(paragraph.getroottree().getelementpath(paragraph))
        if slot is None:
            raise ValueError(f"year paragraph {index} lacks a bookmark")
        matches = tuple(re.finditer(r"\b20\d{2}\b", visible_text(paragraph)))
        if not 1 <= len(matches) <= 2:
            raise ValueError(f"year paragraph {index} changed")
        spans.extend(
            YearSpan(slot, match.start(), match.end(), int(match.group()) - 2025)
            for match in matches
        )
    output.write_text(json.dumps([asdict(item) for item in spans]), encoding="utf-8")


def _unit(data: PieeData, key: str) -> str:
    source_unit = next(iter(data.dataset.production_unit.values()), "")
    unit = "mii MWh" if source_unit.startswith("mii MWh") else source_unit
    if key == "production":
        return f"{unit}/an" if unit else ""
    if key.startswith("specific_"):
        return f"tep/{unit}" if unit else ""
    return "tone/an" if key == "fuel" else "MWh/an"


def _value(data: PieeData, key: str, year_offset: int) -> float | None:
    number = CHARTS[key]
    binding = next(item for item in BINDINGS if item.slot == f"chart_{number}")
    series = chart_series(data, binding)[0]
    return series.values[year_offset + 2] if series is not None else None


def render_number_spans(
    source: Path, manifest: Path, data: PieeData, output: Path, ledger: AnchorLedger
) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    for raw in json.loads(manifest.read_text(encoding="utf-8")):
        item = NumberSpan(**raw)
        paragraph = find([root], item.slot)
        amount = _value(data, item.key, item.year_offset)
        unit = _unit(data, item.key)
        rendered = (
            f"{prototype_number(amount, item.decimals)} {unit}"
            if amount is not None and unit
            else "n.d."
        )
        replace_spans(
            paragraph,
            (
                TextSpan(item.year_start, item.year_end, str(data.year + item.year_offset)),
                TextSpan(item.value_start, item.value_end, rendered, amount is None or not unit),
            ),
        )
        ledger.record(item.slot)
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)


def render_year_spans(
    source: Path, manifest: Path, data: PieeData, output: Path, ledger: AnchorLedger
) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    grouped: dict[str, list[YearSpan]] = {}
    for raw in json.loads(manifest.read_text(encoding="utf-8")):
        item = YearSpan(**raw)
        grouped.setdefault(item.slot, []).append(item)
    for slot, items in grouped.items():
        replace_spans(
            find([root], slot),
            tuple(TextSpan(item.start, item.end, str(data.year + item.offset)) for item in items),
        )
        ledger.record(slot)
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
