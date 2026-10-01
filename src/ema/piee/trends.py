"""S7 trend directions placed in authored PIEE observation paragraphs."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from docx.oxml.ns import qn

from ema.consumption_analysis.phrases import trend_direction
from ema.core.office.anchors import AnchorLedger, find
from ema.core.office.base_map import BaseMap
from ema.core.office.cell_text import set_paragraph_text
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.office.run_range import TextSpan, replace_spans, visible_text
from ema.piee.chart_plan import BINDINGS, chart_series
from ema.piee.dataset import PieeData

TREND_CHARTS = {58: 4, 112: 8, 146: 12, 193: 16, 230: 20, 359: 30, 387: 31}
OTHER_TREND_CHARTS = {
    35: 1,
    40: 2,
    45: 3,
    89: 5,
    94: 6,
    99: 7,
    170: 13,
    175: 14,
    180: 15,
    207: 17,
    212: 18,
    217: 19,
    302: 25,
    314: 26,
    325: 27,
    336: 28,
}


@dataclass(frozen=True)
class TrendSpan:
    slot: str
    start: int
    end: int
    chart_number: int
    year_start: int | None = None
    year_end: int | None = None


def build_trend_spans(parts: dict[str, bytes], mapping: BaseMap, output: Path) -> None:
    body = xml(parts, "word/document.xml").find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE base has no body")
    slots = {entry.selector: entry.slot for entry in mapping.elements if entry.kind == "paragraph"}
    result: list[TrendSpan] = []
    for index, chart_number in TREND_CHARTS.items():
        paragraph = list(body)[index - 1]
        slot = slots.get(paragraph.getroottree().getelementpath(paragraph))
        if slot is None:
            raise ValueError(f"trend paragraph {index} lacks bookmark")
        content = visible_text(paragraph)
        trend = re.search(r"\b(?:creștere|scădere)\b", content, re.I)
        if trend is None:
            raise ValueError(f"trend paragraph {index} lacks trend word")
        year = re.search(r"\b20\d{2}\b", content) if index == 387 else None
        result.append(
            TrendSpan(
                slot,
                trend.start(),
                trend.end(),
                chart_number,
                year.start() if year else None,
                year.end() if year else None,
            )
        )
    output.write_text(json.dumps([asdict(item) for item in result]), encoding="utf-8")


def render_trends(  # noqa: C901, PLR0912
    source: Path, manifest: Path, data: PieeData, output: Path, ledger: AnchorLedger
) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    for raw in json.loads(manifest.read_text(encoding="utf-8")):
        item = TrendSpan(**raw)
        paragraph = find([root], item.slot)
        binding = next(x for x in BINDINGS if x.slot == f"chart_{item.chart_number}")
        series = chart_series(data, binding)[0]
        values: list[float | None] = (
            list(series.values) if series is not None else [None, None, None]
        )
        direction = trend_direction(values, 4 if item.chart_number in (30,) else 2)
        if direction is None:
            set_paragraph_text(paragraph, "n.d.", missing=True)
        elif direction == "constant":
            set_paragraph_text(
                paragraph,
                (
                    "Conform figurii numărul 3 d) se observă că valoarea anuală a consumului "
                    "de energie electrică din parcul fotovoltaic propriu s-a menținut "
                    "constantă în perioada de analiză."
                    if item.chart_number == 12
                    else "Din figura de mai sus se observă că valoarea s-a menținut constantă."
                ),
            )
        else:
            spans = [
                TextSpan(item.start, item.end, "creștere" if direction == "growth" else "scădere")
            ]
            if item.year_start is not None and item.year_end is not None:
                years = (data.year - 2, data.year - 1, data.year)
                observed = [
                    (year, value)
                    for year, value in zip(years, values, strict=True)
                    if value is not None
                ]
                if observed:
                    maximum = max(observed, key=lambda pair: (pair[1], pair[0]))[0]
                    spans.append(TextSpan(item.year_start, item.year_end, str(maximum)))
            replace_spans(paragraph, tuple(spans))
        ledger.record(item.slot)
    for index, chart_number in OTHER_TREND_CHARTS.items():
        body = root.find(qn("w:body"))
        if body is None:
            raise ValueError("PIEE body is missing")
        if f"chart_{chart_number}" in ledger.expected:
            chart = find([root], f"chart_{chart_number}")
            paragraph = chart
            for _ in range(3):
                paragraph = paragraph.getnext()
                if paragraph is None:
                    break
        else:
            paragraph = list(body)[index - 1]
        if paragraph is None:
            raise ValueError(f"trend paragraph for chart {chart_number} missing")
        content = visible_text(paragraph)
        trend = re.search(r"\b(?:creștere|scădere)\b", content, re.I)
        if trend is None:
            raise ValueError(f"trend paragraph {index} changed")
        binding = next(x for x in BINDINGS if x.slot == f"chart_{chart_number}")
        series = chart_series(data, binding)[0]
        direction = trend_direction(list(series.values) if series is not None else [], 2)
        if direction is None:
            set_paragraph_text(paragraph, "n.d.", missing=True)
        elif direction == "constant":
            set_paragraph_text(
                paragraph, "Din figura de mai sus se observă că valoarea s-a menținut constantă."
            )
        else:
            replace_spans(
                paragraph,
                (
                    TextSpan(
                        trend.start(),
                        trend.end(),
                        "creștere" if direction == "growth" else "scădere",
                    ),
                ),
            )
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
