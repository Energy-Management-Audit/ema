"""Write a mapped Word cell while retaining its authored paragraph and run style."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.run_range import TextSpan, replace_spans, visible_text


def set_paragraph_text(paragraph: etree._Element, text: str, *, missing: bool = False) -> None:
    if paragraph.tag != qn("w:p"):
        raise ValueError("mapped target is not a paragraph")
    original = visible_text(paragraph)
    if original:
        replace_spans(paragraph, (TextSpan(0, len(original), text, missing),))
        return
    run = etree.Element(qn("w:r"))
    if missing:
        props = etree.SubElement(run, qn("w:rPr"))
        colour = etree.SubElement(props, qn("w:color"))
        colour.set(qn("w:val"), "FF0000")
    value = etree.SubElement(run, qn("w:t"))
    value.text = text
    paragraph.append(run)


def set_cell_text(cell: etree._Element, text: str, *, missing: bool = False) -> None:
    paragraphs = cell.findall(qn("w:p"))
    if len(paragraphs) != 1:
        raise ValueError("mapped cell needs one paragraph")
    set_paragraph_text(paragraphs[0], text, missing=missing)
