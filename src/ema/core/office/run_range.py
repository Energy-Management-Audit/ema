"""Replace mapped character spans inside existing Word runs without paragraph rebuilding."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
from dataclasses import dataclass

from docx.oxml.ns import qn
from lxml import etree


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str
    missing: bool = False


def visible_text(paragraph: etree._Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(qn("w:t")))


def _text_run(prototype: etree._Element, text: str, *, red: bool) -> etree._Element:
    run = copy.deepcopy(prototype)
    for child in list(run):
        if child.tag != qn("w:rPr"):
            run.remove(child)
    props = run.find(qn("w:rPr"))
    if props is None:
        props = etree.Element(qn("w:rPr"))
        run.insert(0, props)
    if red:
        colour = props.find(qn("w:color"))
        if colour is None:
            colour = etree.SubElement(props, qn("w:color"))
        colour.set(qn("w:val"), "FF0000")
    value = etree.SubElement(run, qn("w:t"))
    value.text = text
    value.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return run


def _replace_one(paragraph: etree._Element, span: TextSpan) -> None:
    nodes = list(paragraph.iter(qn("w:t")))
    positions: list[tuple[int, int, etree._Element]] = []
    offset = 0
    for node in nodes:
        end = offset + len(node.text or "")
        positions.append((offset, end, node))
        offset = end
    if span.start < 0 or span.end > offset or span.start >= span.end:
        raise ValueError("mapped text span is outside its paragraph")
    hit = [
        (first, last, node)
        for first, last, node in positions
        if first < span.end and last > span.start
    ]
    if not hit:
        raise ValueError("mapped text span covers no text")
    first_start, _, first_node = hit[0]
    _, last_end, last_node = hit[-1]
    prefix = (first_node.text or "")[: span.start - first_start]
    suffix = (last_node.text or "")[len(last_node.text or "") - (last_end - span.end) :]
    if first_node is last_node:
        first_node.text = prefix if span.missing else prefix + span.text + suffix
    else:
        first_node.text = prefix + ("" if span.missing else span.text)
        for _, _, node in hit[1:-1]:
            node.text = ""
        last_node.text = suffix
    if span.missing:
        run = first_node.getparent()
        if run is None or run.tag != qn("w:r"):
            raise ValueError("mapped missing span is not in a Word run")
        parent = run.getparent()
        if parent is None:
            raise ValueError("mapped missing span has no run parent")
        index = parent.index(run)
        parent.insert(index + 1, _text_run(run, span.text, red=True))
        if first_node is last_node and suffix:
            parent.insert(index + 2, _text_run(run, suffix, red=False))
    first_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    last_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def replace_spans(paragraph: etree._Element, spans: tuple[TextSpan, ...]) -> None:
    """Use offsets recorded while building the base, never original words as locators."""
    previous = 0
    for span in sorted(spans, key=lambda item: item.start):
        if span.start < previous:
            raise ValueError("mapped text spans overlap")
        previous = span.end
    for span in sorted(spans, key=lambda item: item.start, reverse=True):
        _replace_one(paragraph, span)
