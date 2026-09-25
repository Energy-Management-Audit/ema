"""A rebuilt audit TOC has matching bookmarks, links, and printed chapters."""

import re

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ema.audit.base_toc import refresh_toc
from ema.audit.headings import Heading, MappedHeading


def _styled_toc(document: Document, level: int) -> None:
    paragraph = document.add_paragraph("stale page 99")
    style = OxmlElement("w:pStyle")
    style.set(qn("w:val"), f"TOC{level}")
    paragraph._p.get_or_add_pPr().append(style)


def _bookmark(paragraph: object, name: str, number: int) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(number))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(number))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def test_refresh_toc_rewrites_chapter_number_and_page_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = Document()
    _styled_toc(document, 1)
    _styled_toc(document, 2)
    chapter = document.add_paragraph("6. Indicatori")
    subsection = document.add_paragraph("6.1. Consum")
    _bookmark(chapter, "_old", 2)
    _bookmark(subsection, "_ema_approved", 3)
    spans = [
        (MappedHeading(Heading(0, chapter.text, (), 2), "ch6"), 2, 3),
        (MappedHeading(Heading(1, subsection.text, (), 3), "ch6.indicatori"), 3, 4),
    ]
    monkeypatch.setattr("ema.audit.base_toc.heading_spans_document", lambda doc: spans)
    refresh_toc(document)

    assert chapter.text == "5. Indicatori"
    assert subsection.text == "5.1. Consum"
    root = document.element
    names = {node.get(qn("w:name")) for node in root.iter(qn("w:bookmarkStart"))}
    links = {node.get(qn("w:anchor")) for node in root.iter(qn("w:hyperlink"))}
    refs = {
        match
        for node in root.iter(qn("w:instrText"))
        for match in re.findall(r"PAGEREF\s+(_Toc\d+)", node.text or "")
    }
    assert "_old" not in names
    assert "_ema_approved" in names
    assert links == refs == {name for name in names if name.startswith("_Toc")}
    assert len(links) == 2
    assert "stale page 99" not in " ".join(paragraph.text for paragraph in document.paragraphs)


def test_refresh_toc_requires_prototypes(monkeypatch: pytest.MonkeyPatch) -> None:
    document = Document()
    document.add_paragraph("6. Indicatori")
    monkeypatch.setattr("ema.audit.base_toc.heading_spans_document", lambda doc: [])
    with pytest.raises(ValueError, match="no TOC prototypes"):
        refresh_toc(document)
