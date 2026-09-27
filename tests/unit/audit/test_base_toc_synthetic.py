"""A rebuilt audit TOC has matching bookmarks, links, and printed chapters."""

import re

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ema.audit.base_toc import DEFAULT_TOC, refresh_toc
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
    document.add_paragraph("6.1. Consum")
    monkeypatch.setattr("ema.audit.base_toc.heading_spans_document", lambda doc: [])
    with pytest.raises(ValueError, match="no TOC prototypes"):
        refresh_toc(document)


def _toc_fields(document: Document) -> list[tuple[str, str]]:
    """(kind, instruction) of each outermost field in body order."""
    result: list[tuple[str, str]] = []
    depth = 0
    for node in document.element.body.iter(qn("w:fldChar"), qn("w:instrText")):
        if node.tag == qn("w:instrText"):
            if depth == 1 and (node.text or "").strip().startswith("TOC"):
                result.append(("toc", node.text or ""))
            continue
        kind = node.get(qn("w:fldCharType"))
        depth += 1 if kind == "begin" else -1 if kind == "end" else 0
    assert depth == 0
    return result


def _field(paragraph: object, kind: str, instruction: str | None = None) -> None:
    run = OxmlElement("w:r")
    char = OxmlElement("w:fldChar")
    char.set(qn("w:fldCharType"), kind)
    run.append(char)
    paragraph._p.append(run)  # type: ignore[attr-defined]
    if instruction is not None:
        code = OxmlElement("w:r")
        text = OxmlElement("w:instrText")
        text.text = instruction
        code.append(text)
        paragraph._p.append(code)  # type: ignore[attr-defined]


def _spans(document: Document) -> list[tuple[MappedHeading, int, int]]:
    body = list(document.element.body)
    chapter = next(i for i, e in enumerate(body) if "Indicatori" in "".join(e.itertext()))
    return [
        (MappedHeading(Heading(0, "6. Indicatori", (), chapter), "ch6"), chapter, chapter + 2),
        (
            MappedHeading(Heading(1, "6.1. Consum", (), chapter + 1), "ch6.indicatori"),
            chapter + 1,
            chapter + 2,
        ),
    ]


def test_refresh_toc_keeps_one_toc_field_with_the_base_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = Document()
    _styled_toc(document, 1)
    _styled_toc(document, 2)
    toc_one = document.paragraphs[0]
    _field(toc_one, "begin", ' TOC \\o "1-3" \\h \\z \\u ')
    _field(toc_one, "separate")
    closing = document.add_paragraph("after the table of contents")
    _field(closing, "end")
    document.add_paragraph("6. Indicatori")
    document.add_paragraph("6.1. Consum")
    monkeypatch.setattr("ema.audit.base_toc.heading_spans_document", _spans)
    refresh_toc(document)
    assert _toc_fields(document) == [("toc", ' TOC \\o "1-3" \\h \\z \\u ')]
    refresh_toc(document)
    assert _toc_fields(document) == [("toc", ' TOC \\o "1-3" \\h \\z \\u ')]


def test_refresh_toc_without_a_field_gets_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    document = Document()
    _styled_toc(document, 1)
    _styled_toc(document, 2)
    document.add_paragraph("6. Indicatori")
    document.add_paragraph("6.1. Consum")
    monkeypatch.setattr("ema.audit.base_toc.heading_spans_document", _spans)
    refresh_toc(document)
    assert _toc_fields(document) == [("toc", DEFAULT_TOC)]
