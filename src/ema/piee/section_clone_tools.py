"""Reusable XML and chart operations for cloned PIEE sections."""

# pyright: reportPrivateUsage=false, reportUnusedFunction=false

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchors import AnchorLedger, find, stamp
from ema.core.office.cell_text import set_cell_text, set_paragraph_text
from ema.core.office.chart_series import Series
from ema.core.office.charts import clone_chart
from ema.core.office.package import REL_CHART, C, R, relationships, target_part
from ema.energy_data.carriers import WATER_CARRIERS, Carrier
from ema.piee.chart_plan import MONTHS, ChartBinding, chart_series
from ema.piee.dataset import PieeData
from ema.piee.figure_numbering import numbered_caption
from ema.piee.number import prototype_number

VOCABULARY = {
    Carrier.electricity_cogen: (
        "energie electrică produsă prin cogenerare",
        "Analiza consumului de energie electrică produsă prin cogenerare",
        "Consumul de energie electrică produsă prin cogenerare",
    ),
    Carrier.coke: ("cocs", "Analiza consumului de cocs", "Consumul de cocs"),
    Carrier.water_industrial: ("apă industrială", "Analiza consumului de apă industrială", ""),
    Carrier.water_storm: ("apă meteorică", "Analiza consumului de apă meteorică", ""),
}
COGEN_BALANCE = (
    "Conform informațiilor prezentate, energia electrică consumată din cele două surse, "
    "achiziționată din SEN și produsă local prin cogenerare, este în cantitate totală de:"
)
ORDER = (
    Carrier.electricity_cogen,
    Carrier.coke,
    Carrier.water_industrial,
    Carrier.water_storm,
)


def _present(data: PieeData, carrier: Carrier) -> bool:
    return any(
        (series.annual is not None and series.annual.value is not None)
        or any(reading.value is not None for reading in series.months.values())
        for year, series in data.dataset.carriers.get(carrier, {}).items()
        if data.year - 2 <= year <= data.year
    )


@dataclass(frozen=True)
class Figure:
    part: str
    carrier: Carrier | None
    kind: str
    offset: int | None


def _role(
    manifest: dict[str, dict[str, str | list[str]]], group: str, role: str, n: int = 0
) -> str:
    item = manifest[group][role]
    return item[n] if isinstance(item, list) else item


def _clean(node: etree._Element) -> etree._Element:
    duplicate = copy.deepcopy(node)
    for mark in tuple(duplicate.iter()):
        if mark.tag in {qn("w:bookmarkStart"), qn("w:bookmarkEnd")}:
            parent = mark.getparent()
            if parent is not None:
                parent.remove(mark)
    return duplicate


def _track(
    node: etree._Element, slot: str, ledger: AnchorLedger, next_id: list[int]
) -> etree._Element:
    paragraph = next(node.iter(qn("w:p")), None)
    if paragraph is None:
        raise ValueError(f"clone {slot} has no paragraph")
    stamp(paragraph, slot, next_id[0])
    next_id[0] += 1
    ledger.expected = ledger.expected | {slot}
    ledger.record(slot)
    return node


def _paragraph(  # noqa: PLR0913
    root: etree._Element,
    manifest: dict[str, dict[str, str | list[str]]],
    group: str,
    role: str,
    text: str,
    slot: str,
    *,
    ledger: AnchorLedger,
    next_id: list[int],
    n: int = 0,
) -> etree._Element:
    prototype = find([root], _role(manifest, group, role, n))
    node = _clean(prototype)
    set_paragraph_text(node, text)
    return _track(node, slot, ledger, next_id)


def _figure_series(data: PieeData, item: Figure) -> Series:
    kind = "water" if item.carrier in WATER_CARRIERS else "carrier"
    if item.kind == "specific":
        kind = "specific"
    elif item.kind == "total":
        kind = "total_tep"
    series = chart_series(data, ChartBinding(item.part, kind, item.carrier, item.offset))[0]
    if series is None:
        raise ValueError(f"sourced figure has no series: {item.carrier} {item.kind}")
    return series


def _figures(data: PieeData) -> list[Figure]:
    result: list[Figure] = []
    for carrier in ORDER:
        if not _present(data, carrier):
            continue
        if carrier in WATER_CARRIERS and not data.layout.water_monthly:
            offsets: tuple[int | None, ...] = (None,)
        else:
            offsets = (-2, -1, 0, None)
        style = "water" if carrier in WATER_CARRIERS else "gas"
        for index, offset in enumerate(offsets):
            source = (21 if style == "water" else 13) + (index if offset is not None else 3)
            result.append(
                Figure(
                    f"word/charts/chart{source}.xml",
                    carrier,
                    "annual" if offset is None else "monthly",
                    offset,
                )
            )
    if data.layout.total_energy_figure:
        result.append(Figure("word/charts/chart16.xml", None, "total", None))
    available = data.layout.specific_carriers
    if _present(data, Carrier.coke) and (available is None or Carrier.coke in available):
        result.append(Figure("word/charts/chart26.xml", Carrier.coke, "specific", None))
    for carrier in (Carrier.water_industrial, Carrier.water_storm):
        if _present(data, carrier):
            result.append(Figure("word/charts/chart29.xml", carrier, "specific", None))
    return result


def _figure_caption(data: PieeData, item: Figure) -> str:
    if item.kind == "total":
        return "Fig. Evoluția cantității totale de energie echivalentă"
    assert item.carrier is not None
    noun = VOCABULARY[item.carrier][0]
    if item.kind == "specific":
        return f"Fig. Evoluția anuală a consumului specific de {noun}"
    if item.kind == "annual":
        return f"Fig. Evoluția anuală a consumului de {noun}"
    return f"Fig. Evoluția lunară a consumului de {noun} în {data.year + (item.offset or 0)}"


def _clone_figures(
    source: Path, data: PieeData, figures: list[Figure], directory: Path
) -> tuple[Path, dict[Figure, str]]:
    current = source
    generated: dict[Figure, str] = {}
    for index, item in enumerate(figures):
        following = directory / f"clone-{index}.docx"
        part = clone_chart(
            current,
            item.part,
            [_figure_series(data, item)],
            None,
            following,
            after_part=item.part,
            caption=numbered_caption(current, _figure_caption(data, item)),
        )
        generated[item] = part
        current = following
    return current, generated


def _take_charts(
    parts: dict[str, bytes], root: etree._Element, generated: dict[Figure, str]
) -> dict[Figure, tuple[etree._Element, etree._Element]]:
    result: dict[Figure, tuple[etree._Element, etree._Element]] = {}
    targets = {
        relation.get("Id"): target_part("word/document.xml", relation.get("Target", ""))
        for relation in relationships(parts, "word/document.xml")
        if relation.get("Type") == REL_CHART
    }
    for item, part in generated.items():
        matched = [
            chart
            for chart in root.iter(f"{{{C}}}chart")
            if targets.get(chart.get(f"{{{R}}}id")) == part
        ]
        if len(matched) != 1:
            raise ValueError(f"cloned chart not uniquely placed: {part}")
        paragraph = next(matched[0].iterancestors(qn("w:p")), None)
        if paragraph is None:
            raise ValueError(f"cloned chart has no paragraph: {part}")
        caption = paragraph.getnext()
        if caption is None or caption.tag != qn("w:p"):
            raise ValueError(f"cloned chart has no caption: {part}")
        result[item] = (paragraph, caption)
    for paragraph, caption in result.values():
        parent = paragraph.getparent()
        if parent is None or caption.getparent() is not parent:
            raise ValueError("cloned chart paragraphs separated")
        parent.remove(paragraph)
        parent.remove(caption)
    return result


def _add_chart(
    nodes: list[etree._Element],
    chart: tuple[etree._Element, etree._Element],
    carrier: Carrier | None,
    name: str,
    ledger: AnchorLedger,
    next_id: list[int],
) -> None:
    label = carrier.value if carrier is not None else "total_energy"
    nodes.append(_track(chart[0], f"{label}_{name}_chart", ledger, next_id))
    nodes.append(_track(chart[1], f"{label}_{name}_caption", ledger, next_id))


def _monthly_table(  # noqa: PLR0913
    root: etree._Element,
    manifest: dict[str, dict[str, str | list[str]]],
    group: str,
    carrier: Carrier,
    half: int,
    data: PieeData,
    *,
    ledger: AnchorLedger,
    next_id: list[int],
) -> etree._Element:
    prototype = find([root], _role(manifest, group, "table", half))
    table = _clean(next(prototype.iterancestors(qn("w:tbl"))))
    rows = table.findall(qn("w:tr"))
    if len(rows) < 4:
        raise ValueError("monthly prototype table has fewer than three years")
    for row_index, row in enumerate(rows[:4]):
        cells = row.findall(qn("w:tc"))
        for column, cell in enumerate(cells[:7]):
            if row_index == 0:
                value = "Anul" if column == 0 else MONTHS[half * 6 + column - 1]
            elif column == 0:
                value = str(data.year - 3 + row_index)
            else:
                series = chart_series(
                    data,
                    ChartBinding(
                        "clone",
                        "water" if carrier in WATER_CARRIERS else "carrier",
                        carrier,
                        row_index - 3,
                    ),
                )[0]
                number = series.values[half * 6 + column - 1] if series else None
                value = (
                    prototype_number(number, 0 if carrier in WATER_CARRIERS else 2)
                    if number is not None
                    else "n.d."
                )
            set_cell_text(cell, value, missing=value == "n.d.")
    return _track(table, f"{carrier.value}_table_{half + 1}", ledger, next_id)


def _insert_before(root: etree._Element, boundary: str, nodes: list[etree._Element]) -> None:
    target = find([root], boundary)
    parent = target.getparent()
    if parent is None:
        raise ValueError(f"boundary {boundary} has no parent")
    position = parent.index(target)
    for node in nodes:
        parent.insert(position, node)
        position += 1


def _remove_before(root: etree._Element, start: str, end: str, ledger: AnchorLedger) -> None:
    first, last = find([root], start), find([root], end)
    parent = first.getparent()
    if parent is None or last.getparent() is not parent:
        raise ValueError(f"section {start} boundaries changed")
    for node in list(parent)[parent.index(first) : parent.index(last)]:
        for mark in node.iter(qn("w:bookmarkStart")):
            name = (mark.get(qn("w:name")) or "").removeprefix("_ema_")
            if name in ledger.expected:
                ledger.record(name, removed=True)
        parent.remove(node)
