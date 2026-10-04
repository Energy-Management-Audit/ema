"""Fill the ch. 2-3 tables and ch. 2 charts of the anchored base from the Necesar info fields.

Each table keeps its prototype row: one clone per data row, the rest removed. A value the
sources do not hold is a red n.d.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document
from lxml import etree

from ema.audit.base_units import heading_spans_document
from ema.audit.chapter_tables_data import (
    EMPLOYEES,
    TURNOVER,
    Cell,
    boiler_rows,
    vehicle_rows,
    yearly,
)
from ema.audit.heading_titles import MARKER
from ema.core.errors import EmaError
from ema.core.office.block_text import set_text
from ema.core.office.blocks import ElementLocator, NativeChart, Prototypes, render
from ema.core.office.chart_blocks import import_chart_style
from ema.core.office.chart_ids import refresh_unique_ids
from ema.core.office.chart_series import Series
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.core.review.models import Field

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MISSING = "n.d."


@dataclass(frozen=True)
class TableSpec:
    section: str
    header: tuple[str, ...]
    # Header rows, then the prototype data row; a numbered table keeps its auto-numbered column.
    header_rows: int = 1
    numbered: bool = False


EMPLOYEES_TABLE = TableSpec(
    "ch2.date_generale", ("An referință", "Numărul mediu total de angajați")
)
TURNOVER_TABLE = TableSpec("ch2.istorie", ("Anul", "Valoare - lei"))
BOILERS_TABLE = TableSpec(
    "ch3.equipment",
    (
        "Nr. Crt",
        "Denumire + tip echipament",
        "Proces de fabricație/deservit",
        "Buc.",
        "Putere instalată - kW",
        "Resursa consumată",
    ),
    header_rows=2,
    numbered=True,
)
VEHICLES_TABLE = TableSpec(
    "ch3.carburant",
    ("Nr. crt", "Tip autovehicul", "Nr. buc.", "Consum în"),
    numbered=True,
)
# The chart under each ch. 2 table, with the unit on its value axis.
CHARTS = (
    (EMPLOYEES_TABLE, "Număr mediu de angajați", "angajați"),
    (TURNOVER_TABLE, "Cifra de afaceri", "lei"),
)


@dataclass(frozen=True)
class Caption:
    key: str
    title: str
    unit: str | None = None


CAPTIONS = {
    EMPLOYEES_TABLE: (
        Caption("employees.table", "Numărul mediu de angajați"),
        Caption("employees.chart", "Evoluția numărului mediu de angajați"),
    ),
    TURNOVER_TABLE: (
        Caption("turnover.table", "Cifra de afaceri", "lei"),
        Caption("turnover.chart", "Evoluția cifrei de afaceri", "lei"),
    ),
    BOILERS_TABLE: (Caption("boilers.table", "Centrale termice"),),
    VEHICLES_TABLE: (Caption("vehicles.table", "Parcul auto"),),
}


def _text(element: etree._Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t"))


def _spans(source: Path) -> dict[str, tuple[int, int]]:
    spans = heading_spans_document(Document(str(source)))
    return {item.section_id: (start, end) for item, start, end in reversed(spans)}


def _table(
    body: Sequence[etree._Element], spans: dict[str, tuple[int, int]], spec: TableSpec
) -> int | None:
    """Find the table whose header identifies this spec, even among other tables."""
    start, end = spans.get(spec.section, (0, 0))

    def normalized(value: str) -> str:
        return re.sub(r"[^\w]+", "", value.casefold())

    for index in range(start, end):
        table = body[index]
        if table.tag != W + "tbl":
            continue
        header = table.find(W + "tr")
        if header is None:
            continue
        cells = header.findall(W + "tc")
        if len(cells) != len(spec.header):
            continue
        actual = [normalized(_text(cell)) for cell in cells]
        expected = [normalized(label) for label in spec.header]
        if all(
            value and (value.startswith(label) or label.startswith(value))
            for value, label in zip(actual, expected, strict=True)
        ):
            return index
    return None


def _set_cell(cell: etree._Element, text: str, *, missing: bool = False) -> None:
    """The cell holds one paragraph: a header the base spread over two keeps the first."""
    for extra in cell.findall(W + "p")[1:]:
        cell.remove(extra)
    set_text(cell, text, missing=missing)


def fill_table(table: etree._Element, spec: TableSpec, rows: Iterable[Sequence[Cell]]) -> None:
    owner = table.getroottree().getroot()
    all_rows = table.findall(W + "tr")
    skip = 1 if spec.numbered else 0
    for cell, text in zip(all_rows[0].findall(W + "tc"), spec.header, strict=True):
        _set_cell(cell, text)
    template = all_rows[spec.header_rows]
    for row in all_rows[spec.header_rows :]:
        table.remove(row)
    for values in rows:
        clone = copy.deepcopy(template)
        refresh_unique_ids(clone, clone, owner)
        for cell, value in zip(clone.findall(W + "tc")[skip:], values, strict=True):
            _set_cell(cell, value or MISSING, missing=value is None)
        table.append(clone)


def _tables(fields: Sequence[Field]) -> list[tuple[TableSpec, list[list[Cell]]]]:
    employees = yearly(fields, EMPLOYEES)
    turnover = yearly(fields, TURNOVER)
    tables = [
        (EMPLOYEES_TABLE, employees.rows),
        (TURNOVER_TABLE, turnover.rows),
        (BOILERS_TABLE, boiler_rows(fields)),
        (VEHICLES_TABLE, vehicle_rows(fields)),
    ]
    return [(spec, rows) for spec, rows in tables if rows]


def _title_captions(
    body: Sequence[etree._Element],
    spans: dict[str, tuple[int, int]],
    spec: TableSpec,
    table: int,
) -> None:
    start, end = spans[spec.section]
    captions = CAPTIONS[spec]
    before = next(
        (
            body[i]
            for i in range(table - 1, start - 1, -1)
            if body[i].tag == W + "p" and re.match(r"^\s*Tabel", _text(body[i]))
        ),
        None,
    )
    if before is None:
        raise EmaError("table_slot", "Legenda tabelului lipseşte din bază.", spec.section)
    caption = captions[0]
    if MARKER in _text(before):
        set_text(
            before,
            _text(before).replace(MARKER, _caption_title(caption)),
        )
    if len(captions) == 2:
        after = next(
            (
                body[i]
                for i in range(table + 1, end)
                if body[i].tag == W + "p" and re.match(r"^\s*Fig", _text(body[i]))
            ),
            None,
        )
        if after is None:
            raise EmaError("chart_slot", "Legenda graficului lipseşte din bază.", spec.section)
        caption = captions[1]
        if MARKER in _text(after):
            set_text(
                after,
                _text(after).replace(MARKER, _caption_title(caption)),
            )


def _caption_title(caption: Caption) -> str:
    return f"{caption.title} ({caption.unit})" if caption.unit else caption.title


def write_tables(
    source: Path,
    target: Path,
    *,
    chapter: str,
    fields: Sequence[Field],
) -> None:
    """The tables of one chapter, filled; a table without data keeps its markers."""
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    body_node = root.find(W + "body")
    assert body_node is not None
    body = list(body_node)
    spans = _spans(source)
    for spec, rows in _tables(fields):
        if not spec.section.startswith(chapter):
            continue
        index = _table(body, spans, spec)
        if index is None:
            raise EmaError("table_slot", "Locul tabelului lipseşte din bază.", spec.section)
        fill_table(body[index], spec, rows)
        _title_captions(body, spans, spec, index)
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, target)


def _slot(body: Sequence[etree._Element], table: int) -> int:
    """The marker paragraph where the chart under the table goes: just above its caption."""
    caption = next(
        (
            i
            for i in range(table + 1, len(body))
            if body[i].tag == W + "p" and re.match(r"^\s*Fig\b", _text(body[i]))
        ),
        None,
    )
    if caption is None or _text(body[caption - 1]).strip() != MARKER:
        raise EmaError("chart_slot", "Locul graficului lipseşte din bază.", str(table))
    return caption - 1


def _drop(path: Path, indexes: list[int]) -> None:
    """Remove the slots, highest first, so each index still points at its own paragraph."""
    parts = read_parts(path)
    root = xml(parts, "word/document.xml")
    body = root.find(W + "body")
    assert body is not None
    for index in sorted(indexes, reverse=True):
        body.remove(list(body)[index])
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, path)


def write_charts(
    source: Path, target: Path, *, fields: Sequence[Field], chart_source: Path
) -> None:
    """The employees and turnover charts, in the style of the base's own ch. 4 bar charts."""
    parts = read_parts(source)
    body = list(xml(parts, "word/document.xml").find(W + "body"))  # type: ignore[arg-type]
    spans = _spans(source)
    data = {EMPLOYEES_TABLE: yearly(fields, EMPLOYEES), TURNOVER_TABLE: yearly(fields, TURNOVER)}
    slots: list[tuple[int, Series, str]] = []
    for spec, name, unit in CHARTS:
        table = _table(body, spans, spec)
        series = data[spec]
        if table is not None and series.years:
            categories = [str(year) for year in series.years]
            slots.append((_slot(body, table), Series(name, categories, series.values), unit))
    if not slots:
        write_parts(parts, target)
        return
    style, drawing = import_chart_style(chart_source, parts)
    write_parts(parts, target)
    slots.sort(key=lambda slot: slot[0])
    _drop(target, [index for index, _, _ in slots])
    with TemporaryDirectory() as directory:
        current = Path(directory) / "current.docx"
        # Dropping the slots above shifted each later one up by the number dropped before it.
        for order, (index, series, unit) in reversed(list(enumerate(slots))):
            current.write_bytes(target.read_bytes())
            chart = NativeChart("chart", style, [series], column_axis_title=unit)
            locator = ElementLocator(index - order)
            render(current, target, locator, [chart], Prototypes({"chart": drawing}, 2))
