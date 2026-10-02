"""Independent chart-layout assertions for S17c generated final documents."""

import re
from collections import Counter
from pathlib import Path

import pdfplumber
from docx import Document
from docx.text.paragraph import Paragraph
from lxml import etree

from ema.audit.base_units import heading_spans_document
from ema.audit.chapter_four_blocks import EMISSIONS_MISSING, NO_SERIES
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


def _assert_value_cell(cell: etree._Element) -> None:
    text = "".join(node.text or "" for node in cell.iter(W + "t"))
    red = any(node.get(W + "val") == "FF0000" for node in cell.iter(W + "color"))
    if text == TABLE_MISSING_TEXT:
        flag = cell.find(W + "tcPr/" + W + "noWrap")
        assert flag is not None and flag.get(W + "val", "1") in {"1", "true", "on"}
        assert cell.find(W + "p/" + W + "pPr/" + W + "jc").get(W + "val") == "center"
        assert red
    elif text == EMISSIONS_MISSING:  # 4.6: a red n.d. on the row, no table note
        assert red
    elif text != NO_SERIES:
        assert re.fullmatch(r"-?\d{1,3}(?:\.\d{3})*,\d{2}", text), text


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
                _assert_value_cell(cell)
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


def assert_production_values_fit_pdf(docx: Path, pdf: Path) -> None:
    """Word keeps each long production value on one line within the six-month table."""
    document = Document(str(docx))
    span = next(
        (start, end)
        for item, start, end in heading_spans_document(document)
        if item.section_id == "ch4.productie"
    )
    expected: Counter[str] = Counter()
    for table in list(document.element.body)[span[0] : span[1]]:
        if table.tag != W + "tbl":
            continue
        assert len(table.findall(W + "tblGrid/" + W + "gridCol")) == 7
        for row in table.findall(W + "tr")[1:]:
            for cell in row.findall(W + "tc")[1:]:
                text = "".join(node.text or "" for node in cell.iter(W + "t"))
                if re.fullmatch(r"\d[\d.,]*", text) and len(text) >= 10:
                    expected[text] += 1
    assert expected, "reference production table must exercise long values"
    with pdfplumber.open(pdf) as exported:
        whole = Counter(word["text"] for page in exported.pages for word in page.extract_words())
    fits = all(whole[value] >= count for value, count in expected.items())
    assert fits, "Word wrapped a long production value"
