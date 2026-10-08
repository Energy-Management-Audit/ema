"""Chapter-four pagination and table geometry, independent of heading placement."""

# pyright: reportPrivateUsage=false

import re

from docx.document import Document as DocumentObject
from lxml import etree

from ema.audit.base_units import heading_spans_document
from ema.audit.chapter_four_comments import ANNUAL_OPENING, FACTOR_LEAD
from ema.audit.chapter_four_resources import TITLES
from ema.core.errors import EmaError
from ema.core.office.missing_text import MISSING_TEXT, TABLE_MISSING_TEXT
from ema.core.office.paragraph_properties import keep_paragraph

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# Her lead-ins stay on the page of the figure, table or list they open.
LEAD_INS = (
    "În figura numărul 4.",
    "În tabelul numărul 4.",
    ANNUAL_OPENING,
    *FACTOR_LEAD.values(),
)

_BEFORE = {
    "jc": (
        "textDirection",
        "textAlignment",
        "textboxTightWrap",
        "outlineLvl",
        "divId",
        "cnfStyle",
        "rPr",
        "sectPr",
        "pPrChange",
    ),
    "tblW": (
        "jc",
        "tblCellSpacing",
        "tblInd",
        "tblBorders",
        "shd",
        "tblLayout",
        "tblCellMar",
        "tblLook",
        "tblPrChange",
    ),
    "tcW": (
        "gridSpan",
        "hMerge",
        "vMerge",
        "tcBorders",
        "shd",
        "noWrap",
        "tcMar",
        "textDirection",
        "tcFitText",
        "vAlign",
        "hideMark",
        "tcPrChange",
    ),
    "tblInd": (
        "tblBorders",
        "shd",
        "tblLayout",
        "tblCellMar",
        "tblLook",
        "tblCaption",
        "tblDescription",
    ),
    "tblLayout": ("tblCellMar", "tblLook", "tblCaption", "tblDescription"),
    "noWrap": ("tcMar", "textDirection", "tcFitText", "vAlign", "hideMark"),
    "vAlign": ("hideMark", "headers", "tcPrChange"),
}


def _property(owner: etree._Element, container: str, name: str) -> etree._Element:
    properties = owner.find(W + container)
    if properties is None:
        properties = etree.Element(W + container)
        owner.insert(0, properties)
    item = properties.find(W + name)
    if item is None:
        item = etree.Element(W + name)
        before = {W + tag for tag in _BEFORE.get(name, ())}
        following = next((node for node in properties if node.tag in before), None)
        if following is None:
            properties.append(item)
        else:
            following.addprevious(item)
    return item


def _missing_cell(cell: etree._Element, missing_text: str) -> None:
    text = "".join(node.text or "" for node in cell.iter(W + "t"))
    if text in {missing_text, TABLE_MISSING_TEXT}:
        _property(cell, "tcPr", "noWrap").set(W + "val", "1")
    if text == TABLE_MISSING_TEXT:
        for paragraph in cell.findall(W + "p"):
            _property(paragraph, "pPr", "jc").set(W + "val", "center")


def _table(
    table: etree._Element, width: int, missing_text: str, *, grow_values: bool = False
) -> None:
    for name, value in (("tblW", width), ("tblInd", 0)):
        item = _property(table, "tblPr", name)
        item.set(W + "type", "dxa")
        item.set(W + "w", str(value))
    _property(table, "tblPr", "tblLayout").set(W + "type", "fixed")
    grid = table.findall(W + "tblGrid/" + W + "gridCol")
    try:
        old = [int(column.get(W + "w", "0")) for column in grid]
    except ValueError as exc:
        raise _layout_error("chapter-four table has an invalid grid width") from exc
    total = sum(old)
    if not total or any(value <= 0 for value in old):
        raise _layout_error("chapter-four table lacks column widths")
    widths = [round(width * value / total) for value in old]
    widths[-1] += width - sum(widths)
    if grow_values:
        widths = _value_widths(table, widths)
    for column, value in zip(grid, widths, strict=True):
        column.set(W + "w", str(value))
    for index, row in enumerate(table.findall(W + "tr")):
        cells = row.findall(W + "tc")
        if len(cells) != len(widths) or any(
            cell.find(W + "tcPr/" + W + tag) is not None
            for cell in cells
            for tag in ("gridSpan", "hMerge", "vMerge")
        ):
            continue
        for cell, value in zip(cells, widths, strict=True):
            cell_width = _property(cell, "tcPr", "tcW")
            cell_width.set(W + "type", "dxa")
            cell_width.set(W + "w", str(value))
            if index:
                _property(cell, "tcPr", "vAlign").set(W + "val", "center")
            _missing_cell(cell, missing_text)


def _layout_error(detail: str) -> EmaError:
    return EmaError("chapter_four_layout", "Capitolul 4 nu a putut fi formatat.", detail)


def _text_width(document: DocumentObject) -> int:
    if not document.sections:
        raise _layout_error("chapter-four document section missing")
    section = document.sections[0]
    if section.page_width is None or section.left_margin is None or section.right_margin is None:
        raise _layout_error("chapter-four text width unavailable in document section 1")
    width = (section.page_width - section.left_margin - section.right_margin) // 635
    if width <= 0:
        raise _layout_error(f"chapter-four text width must be positive: {width} twips")
    return width


def _keep_first_half(table: etree._Element) -> None:
    header = table.find(W + "tr")
    if header is None or "Ianuarie" not in "".join(
        part.text or "" for part in header.iter(W + "t")
    ):
        return
    for row in table.findall(W + "tr"):
        for paragraph in row.findall(".//" + W + "p"):
            keep_paragraph(paragraph, "keepNext")


def format_chapter_four(document: DocumentObject, *, missing_text: str = MISSING_TEXT) -> None:
    """Apply the final layout only inside chapter four; source headings stay in place."""
    spans = heading_spans_document(document)
    positions = {item.section_id: start for item, start, _ in spans}
    start = positions.get("ch4")
    end = positions.get("ch5", positions.get("ch6"))
    if start is None or end is None or end <= start:
        raise _layout_error(f"chapter-four bounds missing: ch4={start}, next chapter={end}")
    width = _text_width(document)
    headings = {index for key, index in positions.items() if key == "ch4" or key.startswith("ch4.")}
    labels = {*TITLES.values(), "Consum total"}
    body = document.element.find(W + "body")
    if body is None:
        raise _layout_error("chapter-four document body missing")
    production_start = positions.get("ch4.productie", -1)
    production_end = min((index for index in headings if index > production_start), default=end)
    for index, node in enumerate(body):
        if not start <= index < end:
            continue
        if node.tag == W + "tbl":
            _table(
                node, width, missing_text, grow_values=production_start <= index < production_end
            )
            _keep_first_half(node)
        elif node.tag == W + "p":
            text = "".join(item.text or "" for item in node.iter(W + "t"))
            if (
                index in headings
                or text in labels
                or text.startswith(LEAD_INS)
                or node.find(".//" + W + "drawing") is not None
            ):
                keep_paragraph(node, "keepNext")
            if text.startswith(("Fig. nr. 4.", "Tabelul 4.")):
                keep_paragraph(node, "keepLines")
                keep_paragraph(node, "keepNext")


def _value_widths(table: etree._Element, widths: list[int]) -> list[int]:
    """Spend spare width on the longest production values, without changing the six-month grid."""
    contents = [0] * len(widths)
    numeric: list[etree._Element] = []
    for row in table.findall(W + "tr")[1:]:
        cells = row.findall(W + "tc")
        if len(cells) != len(widths):
            continue
        for column, cell in enumerate(cells):
            text = "".join(node.text or "" for node in cell.iter(W + "t")).strip()
            if not re.fullmatch(r"[+-]?\d[\d., ]*", text):
                continue
            numeric.append(cell)
            # Times New Roman digits occupy half an em; allow a little rounding space.
            sizes = [int(node.get(W + "val", "24")) for node in cell.iter(W + "sz")]
            half_points = max(sizes, default=24)
            glyphs = sum(5 if char.isdigit() else 2.5 for char in text)
            contents[column] = max(contents[column], round(glyphs * half_points) + 24)
    padding = 108
    # Six long values fit at her font size once surplus cell padding gives way to the text.
    while padding and sum(max(600, size + 2 * padding) for size in contents) > sum(widths):
        padding -= 1
    if padding < 108:
        for cell in numeric:
            margins = _property(cell, "tcPr", "tcMar")
            for side in ("left", "right"):
                margin = margins.find(W + side)
                if margin is None:
                    margin = etree.SubElement(margins, W + side)
                margin.set(W + "type", "dxa")
                margin.set(W + "w", str(padding))
    needed = [max(600, size + 2 * padding) for size in contents]
    return _grow_values(widths, needed)


def _grow_values(widths: list[int], needed: list[int]) -> list[int]:
    result = list(widths)
    for column in sorted(range(1, len(widths)), key=lambda index: needed[index], reverse=True):
        deficit = max(0, needed[column] - result[column])
        for donor in sorted(
            range(len(widths)), key=lambda index: result[index] - needed[index], reverse=True
        ):
            if donor == column:
                continue
            moved = min(deficit, max(0, result[donor] - needed[donor]))
            result[donor] -= moved
            result[column] += moved
            deficit -= moved
            if deficit == 0:
                break
    return result
