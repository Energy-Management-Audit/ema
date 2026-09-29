"""Independent chart-layout assertions for S17c generated final documents."""

import re
from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph
from lxml import etree

from ema.audit.base_units import heading_spans_document
from ema.core.office.chart_series import Series
from ema.core.office.missing_text import TABLE_MISSING_NOTE, TABLE_MISSING_TEXT
from ema.core.office.package import C

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _keep_next(paragraph: Paragraph) -> bool:
    direct = paragraph.paragraph_format.keep_with_next
    if direct is not None:
        return direct
    style = paragraph.style
    while style is not None:
        value = style.paragraph_format.keep_with_next
        if value is not None:
            return value
        style = style.base_style
    return False


def expected_unit(unit: str, specific: bool) -> tuple[str, int]:
    if not specific:
        return unit, 1
    if "/kg" in unit:
        return unit.replace("/kg", "/t", 1), 1000
    if unit.endswith("/1000 lei"):
        return "tep/mil lei", 1000
    if unit.endswith("/lei"):
        return unit.removesuffix("/lei") + "/mil lei", 1_000_000
    return unit, 1


def assert_chart_layout(root: etree._Element, series: list[Series], axis: str) -> None:
    assert root.find(f".//{{{C}}}plotArea/{{{C}}}layout/{{{C}}}manualLayout") is None
    assert root.find(f".//{{{C}}}plotArea/*/{{{C}}}title/{{{C}}}layout/{{{C}}}manualLayout") is None
    points = [value for item in series for value in item.values if value is not None]
    assert any(point != 0 for point in points)
    expected_format = "#,##0.00" if max(points) < 10 else "#,##0"
    assert root.find(f".//{{{C}}}valAx/{{{C}}}numFmt").get("formatCode") == expected_format
    if any(value is None for item in series for value in item.values):
        assert root.find(f".//{{{C}}}trendline") is None
    if all(len(item.categories) == 12 for item in series):
        assert all(len(item.categories) == 12 for item in series)
        category = root.find(f".//{{{C}}}catAx")
        assert category.find(f"{{{C}}}tickLblSkip").get("val") == "1"
        text = category.find(f"{{{C}}}txPr")
        assert text.find(A + "bodyPr").get("rot") == "-2700000"
        font = text.find(A + "p/" + A + "pPr/" + A + "defRPr")
        assert font.get("sz") == "1000"
        assert font.find(A + "latin").get("typeface") == "Times New Roman"


def assert_chapter_tables(docx: Path) -> None:
    document = Document(str(docx))
    spans = heading_spans_document(document)
    start = next(begin for item, begin, _ in spans if item.section_id == "ch4")
    end = next(begin for item, begin, _ in spans if item.section_id in {"ch5", "ch6"})
    for item, begin, _ in spans:
        if item.section_id == "ch4" or item.section_id.startswith("ch4."):
            heading = document.element.body[begin]
            assert _keep_next(Paragraph(heading, document))
    section = document.sections[0]
    width = (section.page_width - section.left_margin - section.right_margin) // 635
    tables = [node for node in list(document.element.body)[start:end] if node.tag == W + "tbl"]
    assert tables
    for table in tables:
        assert table.find(W + "tblPr/" + W + "tblW").get(W + "w") == str(width)
        assert (
            sum(int(col.get(W + "w")) for col in table.findall(W + "tblGrid/" + W + "gridCol"))
            == width
        )
        for row in table.findall(W + "tr")[1:]:
            for cell in row.findall(W + "tc"):
                assert cell.find(W + "tcPr/" + W + "vAlign").get(W + "val") == "center"
            for cell in row.findall(W + "tc")[1:]:
                text = "".join(node.text or "" for node in cell.iter(W + "t"))
                if text == TABLE_MISSING_TEXT:
                    flag = cell.find(W + "tcPr/" + W + "noWrap")
                    assert flag is not None and flag.get(W + "val", "1") in {"1", "true", "on"}
                    assert cell.find(W + "p/" + W + "pPr/" + W + "jc").get(W + "val") == "center"
                    assert any(node.get(W + "val") == "FF0000" for node in cell.iter(W + "color"))
                else:
                    assert re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", text), text
        missing = any(
            "".join(t.text or "" for t in cell.iter(W + "t")) == TABLE_MISSING_TEXT
            for cell in table.iter(W + "tc")
        )
        following = table.getnext()
        text = (
            "".join(t.text or "" for t in following.iter(W + "t")) if following is not None else ""
        )
        assert (text == TABLE_MISSING_NOTE) == missing
        if missing:
            assert any(node.get(W + "val") == "FF0000" for node in following.iter(W + "color"))
