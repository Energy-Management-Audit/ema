"""Instantiate document blocks from existing OOXML prototypes."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from lxml import etree

from ema.core.office.block_text import set_text
from ema.core.office.chart_blocks import build_column_chart_detached, clone_chart_detached
from ema.core.office.chart_ids import refresh_unique_ids
from ema.core.office.chart_series import Series
from ema.core.office.errors import OfficeError
from ema.core.office.numbers_ro import format_number
from ema.core.office.package import encoded, read_parts, write_parts
from ema.core.office.pictures import replace_picture

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
Kind = Literal["fig", "tab"]


@dataclass(frozen=True)
class Num:
    value: float | int | Decimal | None
    decimals: int
    unit: str | None = None
    fact: str | None = None
    grouping: bool = True


@dataclass(frozen=True)
class Ref:
    kind: Kind
    id: str


type Segment = str | Num | Ref


@dataclass(frozen=True)
class Paragraph:
    proto: str
    segments: list[Segment]


@dataclass(frozen=True)
class BulletList:
    proto: str
    items: list[list[Segment]]


@dataclass(frozen=True)
class Table:
    proto: str
    rows: list[list[list[Segment]]]
    header_rows: int = 1
    header: list[list[str]] | None = None


@dataclass(frozen=True)
class Caption:
    proto: str
    kind: Kind
    id: str
    segments: list[Segment]


@dataclass(frozen=True)
class NativeChart:
    proto: str
    part: str
    series: list[Series]
    title: str | None = None
    column_axis_title: str | None = None


@dataclass(frozen=True)
class Figure:
    proto: str
    caption: Caption
    image: Path | None = None


@dataclass(frozen=True)
class PageBreak:
    proto: str


@dataclass(frozen=True)
class Missing:
    proto: str
    text: str


@dataclass(frozen=True)
class Retained:
    """Existing element kept in a region replacement without changing its OOXML ids."""

    proto: str
    fresh: bool = False


type Block = (
    Paragraph | BulletList | Table | Caption | NativeChart | Figure | PageBreak | Missing | Retained
)


@dataclass(frozen=True)
class ElementLocator:
    """One-based body-child index of the element after which blocks are inserted."""

    body_index: int


@dataclass(frozen=True)
class Prototypes:
    elements: dict[str, etree._Element]
    chapter: int
    missing_text: str = "date indisponibile"


@dataclass(frozen=True)
class NumberUse:
    kind: Kind
    id: str
    number: str


@dataclass(frozen=True)
class ValueUse:
    fact: str | None
    text: str
    block: int


@dataclass(frozen=True)
class RenderReport:
    numbers: list[NumberUse]
    values: list[ValueUse]
    chart_parts: list[str]
    issues: list[str]


def _visible(element: etree._Element) -> str:
    return "".join(node.text or "" for node in element.iter(f"{{{W}}}t"))


def _caption_number(element: etree._Element, kind: Kind, chapter: int) -> int | None:
    text = _visible(element).strip()
    lead = r"(?:Tabel(?:ul)?|Fig(?:ura|\.)?)" if kind == "tab" else r"(?:Fig(?:ura|\.)?)"
    if kind == "tab":
        lead = r"Tabel(?:ul)?"
    match = re.match(rf"(?i)^{lead}(?:\s+(?:nr\.|numărul))?\s+{chapter}\.(\d+)\b", text)
    return int(match.group(1)) if match else None


def _numbering(  # noqa: C901
    body: etree._Element, after: int, blocks: list[Block], chapter: int
) -> list[NumberUse]:
    counts: dict[Kind, int] = {"tab": 0, "fig": 0}
    for node in list(body)[:after]:
        if node.tag != f"{{{W}}}p":
            continue
        for kind in ("tab", "fig"):
            number = _caption_number(node, kind, chapter)
            if number is not None:
                counts[kind] = max(counts[kind], number)
    result: list[NumberUse] = []
    ids: set[tuple[Kind, str]] = set()
    for block in blocks:
        caption = block.caption if isinstance(block, Figure) else block
        if not isinstance(caption, Caption):
            continue
        key = (caption.kind, caption.id)
        if key in ids:
            raise OfficeError("numbering_conflict", f"Repeated caption id: {key}")
        ids.add(key)
        counts[caption.kind] += 1
        result.append(NumberUse(caption.kind, caption.id, f"{chapter}.{counts[caption.kind]}"))
    for node in list(body)[after:]:
        if node.tag != f"{{{W}}}p":
            continue
        for kind in ("tab", "fig"):
            number = _caption_number(node, kind, chapter)
            if number is not None and number <= counts[kind]:
                raise OfficeError("numbering_conflict", f"Later {kind} {chapter}.{number}")
    return result


def _prototype(prototypes: Prototypes, key: str, expected: str) -> etree._Element:
    original = prototypes.elements.get(key)
    if original is None or original.tag != f"{{{W}}}{expected}":
        raise OfficeError("block_prototype", f"{key}: expected {expected}")
    return copy.deepcopy(original)


def _refresh_drawing_ids(clone: etree._Element, owner: etree._Element) -> None:
    used = {
        int(node.get("id") or "0")
        for node in owner.iter(f"{{{WP}}}docPr")
        if (node.get("id") or "").isdigit()
    }
    for node in clone.iter(f"{{{WP}}}docPr"):
        fresh = next(value for value in range(1, 2147483647) if value not in used)
        node.set("id", str(fresh))
        used.add(fresh)


def _fresh(clone: etree._Element, owner: etree._Element) -> etree._Element:
    refresh_unique_ids(clone, clone, owner)
    _refresh_drawing_ids(clone, owner)
    return clone


def _segments(
    segments: list[Segment],
    lookup: dict[tuple[Kind, str], str],
    report: list[ValueUse],
    block_index: int,
    missing_text: str,
) -> tuple[str, list[tuple[int, int]], list[str]]:
    pieces: list[str] = []
    missing: list[tuple[int, int]] = []
    length = 0
    for segment in segments:
        if isinstance(segment, str):
            pieces.append(segment)
        elif isinstance(segment, Num):
            absent = segment.value is None
            formatted = (
                missing_text
                if segment.value is None
                else format_number(segment.value, segment.decimals, segment.unit, segment.grouping)
            )
            pieces.append(formatted)
            report.append(ValueUse(segment.fact, formatted, block_index))
            if absent:
                missing.append((length, length + len(formatted)))
        else:
            key = (segment.kind, segment.id)
            if key not in lookup:
                raise OfficeError("block_reference", f"Unknown {segment.kind} id {segment.id}")
            pieces.append(lookup[key])
        length += len(pieces[-1])
    return "".join(pieces), missing, pieces


def _table_rows(  # noqa: PLR0913
    node: etree._Element,
    block: Table,
    lookup: dict[tuple[Kind, str], str],
    values: list[ValueUse],
    block_index: int,
    missing_text: str,
    *,
    owner: etree._Element,
) -> None:
    rows = node.findall(f"{{{W}}}tr")
    if block.header_rows < 0 or len(rows) <= block.header_rows:
        raise OfficeError("block_prototype", "Table needs a first data row")
    if block.header is not None:
        widths = [len(row.findall(f"{{{W}}}tc")) for row in rows[: block.header_rows]]
        if [len(row) for row in block.header] != widths:
            raise OfficeError("block_prototype", "Table header differs from prototype")
        for row, texts in zip(rows, block.header, strict=False):
            for cell, text in zip(row.findall(f"{{{W}}}tc"), texts, strict=True):
                set_text(cell, text)
    template = rows[block.header_rows]
    for row in rows[block.header_rows :]:
        node.remove(row)
    for data in block.rows:
        clone = copy.deepcopy(template)
        cells = clone.findall(f"{{{W}}}tc")
        if len(data) != len(cells):
            raise OfficeError("block_prototype", "Table row width differs from prototype")
        for cell, segments in zip(cells, data, strict=True):
            text, missing, pieces = _segments(segments, lookup, values, block_index, missing_text)
            set_text(cell, text, missing=missing, pieces=pieces)
        node.append(clone)
        _fresh(clone, owner)


def render(  # noqa: C901, PLR0912, PLR0915
    docx: Path,
    out: Path,
    after: ElementLocator,
    blocks: list[Block],
    prototypes: Prototypes,
    *,
    allow_retained: bool = False,
) -> RenderReport:
    if not allow_retained and any(isinstance(block, Retained) for block in blocks):
        raise OfficeError("block_prototype", "Retained blocks require region replacement")
    parts = read_parts(docx)
    root = etree.fromstring(parts["word/document.xml"])
    body = root.find(f"{{{W}}}body")
    if body is None or after.body_index < 1 or after.body_index > len(body):
        raise OfficeError("block_prototype", "Invalid insertion locator")
    numbers = (
        _numbering(body, after.body_index, blocks, prototypes.chapter)
        if any(isinstance(block, Caption | Figure) for block in blocks)
        else []
    )
    lookup: dict[tuple[Kind, str], str] = {
        (number.kind, number.id): number.number for number in numbers
    }
    values: list[ValueUse] = []
    chart_parts: list[str] = []
    detached: dict[int, etree._Element] = {}
    with TemporaryDirectory() as directory:
        current = Path(directory) / "current.docx"
        next_path = Path(directory) / "next.docx"
        write_parts(parts, current)
        for index, block in enumerate(blocks):
            if not isinstance(block, NativeChart):
                continue
            proto = _prototype(prototypes, block.proto, "p")
            if block.column_axis_title is None:
                part, paragraph = clone_chart_detached(
                    current, block.part, block.series, block.title, next_path, proto
                )
            else:
                part, paragraph = build_column_chart_detached(
                    current, block.part, block.series, block.column_axis_title, next_path, proto
                )
            chart_parts.append(part)
            detached[index] = paragraph
            current, next_path = next_path, current
        parts = read_parts(current)
    cursor = after.body_index
    for index, block in enumerate(blocks):
        nodes: list[etree._Element] = []
        if isinstance(block, NativeChart):
            nodes = [detached[index]]
        elif isinstance(block, Retained):
            original = prototypes.elements.get(block.proto)
            if original is None or original.tag not in {f"{{{W}}}p", f"{{{W}}}tbl"}:
                raise OfficeError("block_prototype", f"Invalid retained element: {block.proto}")
            nodes = [copy.deepcopy(original)]
        elif isinstance(block, BulletList):
            for item in block.items:
                node = _prototype(prototypes, block.proto, "p")
                text, missing, pieces = _segments(
                    item, lookup, values, index, prototypes.missing_text
                )
                set_text(node, text, missing=missing, pieces=pieces)
                nodes.append(node)
        elif isinstance(block, Table):
            node = _prototype(prototypes, block.proto, "tbl")
            _table_rows(node, block, lookup, values, index, prototypes.missing_text, owner=root)
            nodes = [node]
        elif isinstance(block, Missing):
            node = _prototype(prototypes, block.proto, "p")
            set_text(node, block.text, missing=True)
            nodes = [node]
        elif isinstance(block, Figure):
            caption = _prototype(prototypes, block.caption.proto, "p")
            text, missing, pieces = _segments(
                block.caption.segments, lookup, values, index, prototypes.missing_text
            )
            set_text(caption, text, missing=missing, pieces=pieces)
            picture = _prototype(prototypes, block.proto, "p")
            if block.image is not None:
                replace_picture(parts, picture, block.image)
            nodes = [picture, caption]
        elif isinstance(block, PageBreak):
            nodes = [_prototype(prototypes, block.proto, "p")]
        else:
            node = _prototype(prototypes, block.proto, "p")
            text, missing, pieces = _segments(
                block.segments, lookup, values, index, prototypes.missing_text
            )
            set_text(node, text, missing=missing, pieces=pieces)
            nodes = [node]
        for node in nodes:
            body.insert(cursor, node)
            if not isinstance(block, Retained) or block.fresh:
                _fresh(node, root)
            cursor += 1
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, out)
    return RenderReport(numbers, values, chart_parts, [])
