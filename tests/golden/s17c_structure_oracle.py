"""Structure acceptance against the body's printed numbering and the Word PDF."""

import re
from collections import defaultdict
from pathlib import Path

import pdfplumber
from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from ema.audit.base_numbering import effective_indent, printed_numbers
from ema.audit.base_units import heading_spans_document


def _assert_heading_format(document, paragraph, level):
    formatted = Paragraph(paragraph, document)
    alignment = formatted.alignment
    style = formatted.style
    while style is not None:
        if alignment is None:
            alignment = style.paragraph_format.alignment
        style = style.base_style
    left, hanging = effective_indent(document, paragraph)
    assert left - hanging == {1: 360, 2: 66, 3: 360}[level]
    if level == 1:
        assert not paragraph.xpath("./w:pPr/w:ind")
    if level > 1:
        # Word omits redundant left alignment; no inherited value means left.
        assert alignment in (None, 0)


def assert_final_structure(docx: Path, pdf: Path) -> tuple[int, int]:
    document = Document(docx)
    body = list(document.element.body)
    heading = next(p for p in body if p.tag == qn("w:p") and _text(p).upper() == "CUPRINS")
    entries = [p for p in body if p.tag == qn("w:p") and p.xpath("./w:hyperlink")]
    assert body.index(entries[0]) == body.index(heading) + 1
    assert _text(entries[0]).startswith("Cuprins")
    assert body[body.index(heading) - 1].xpath('.//w:br[@w:type="page"]')
    numbers = printed_numbers(document)
    anchors = {
        node.get(qn("w:name")): node.getparent()
        for node in document.element.iter(qn("w:bookmarkStart"))
    }
    for entry in entries[1:]:
        link = entry.find(qn("w:hyperlink"))
        target = anchors[link.get(qn("w:anchor"))]
        assert _text(link).startswith(numbers[target])
        assert _text(link).split(numbers[target], 1)[0] == ""
    groups = defaultdict(list)
    added = {}
    for item, start, _ in heading_spans_document(document):
        paragraph = body[start]
        label = numbers[paragraph]
        level = len(label.rstrip(".").split("."))
        _assert_heading_format(document, paragraph, level)
        if level <= 2:
            assert _text(paragraph) == _text(paragraph).upper()
        if item.section_id.startswith("ch4."):
            parent, _, number = label.rstrip(".").rpartition(".")
            groups[parent].append(int(number))
            added[item.section_id] = label
    assert all(values == list(range(1, len(values) + 1)) for values in groups.values())
    assert added["ch4.electricitate_pv"] == "4.2.2."
    assert added["ch4.echiv_pv"] == "4.3.2."
    assert added["ch4.specific_pv"] == "4.5.2."
    assert added["ch4.bilant_real"] == "4.7."
    with pdfplumber.open(pdf) as exported:
        pages = len(exported.pages)
        rendered_pages = [page.extract_text() or "" for page in exported.pages]
        referenced_pages = [
            int(node.text)
            for entry in entries
            for node in entry.xpath("./w:r/w:t")
            if node.text and node.text.strip().isdigit()
        ]
        assert len(referenced_pages) == len(entries)
        assert pages >= max(referenced_pages)
        for entry in entries[1:]:
            link = entry.find(qn("w:hyperlink"))
            target = anchors[link.get(qn("w:anchor"))]
            page = next(
                int(node.text)
                for node in entry.xpath("./w:r/w:t")
                if node.text and node.text.strip().isdigit()
            )
            rendered = rendered_pages[page - 1]
            assert re.search(r"(?m)^\s*" + re.escape(numbers[target]) + r"\s", rendered), numbers[
                target
            ]
        # Body text proves the chapter was retained with its replayed source content.
        text = "\n".join(rendered_pages)
        assert "Societatea Atelier Exemplu SRL are" in text
        assert "4.3.2." in text and "4.5.2." in text and "4.7." in text
    return pages, len(entries)


def _text(paragraph):
    return "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
