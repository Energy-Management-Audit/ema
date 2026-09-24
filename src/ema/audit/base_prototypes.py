"""Carry prototype styles and numbering across audit documents without collisions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from docx.oxml.ns import qn

_STYLE_REFS = {qn(f"w:{tag}") for tag in ("pStyle", "rStyle", "tblStyle", "numStyle")}
_DEPENDENCIES = {qn(f"w:{tag}") for tag in ("basedOn", "next", "link")}


def import_formatting(  # noqa: C901, PLR0915
    target: Any, source: Any, elements: list[Any]
) -> None:
    """Remap source style and num IDs in cloned elements to local definitions."""
    target_styles = target.styles.element
    source_styles = source.styles.element
    target_numbering = target.part.numbering_part.element
    source_numbering = source.part.numbering_part.element
    style_map: dict[str, str] = {}
    number_map: dict[str, str] = {}
    abstract_map: dict[str, str] = {}
    used_style_ids = {item.get(qn("w:styleId")) for item in target_styles.iter(qn("w:style"))}
    used_nums = {int(item.get(qn("w:numId"), "0")) for item in target_numbering.iter(qn("w:num"))}
    used_abstract = {
        int(item.get(qn("w:abstractNumId"), "0"))
        for item in target_numbering.iter(qn("w:abstractNum"))
    }

    def style(old: str) -> str:
        if old in style_map:
            return style_map[old]
        original = next(
            (
                node
                for node in source_styles.iter(qn("w:style"))
                if node.get(qn("w:styleId")) == old
            ),
            None,
        )
        if original is None:
            return old
        number = len(style_map) + 1
        new = f"EmaPrototype{number}"
        while new in used_style_ids:
            number += 1
            new = f"EmaPrototype{number}"
        used_style_ids.add(new)
        style_map[old] = new
        copied = deepcopy(original)
        copied.set(qn("w:styleId"), new)
        target_styles.append(copied)
        for node in copied.iter():
            if node.tag in _DEPENDENCIES and (value := node.get(qn("w:val"))):
                node.set(qn("w:val"), style(value))
            elif node.tag == qn("w:numId") and (value := node.get(qn("w:val"))):
                node.set(qn("w:val"), num(value))
        return new

    def abstract(old: str) -> str:
        if old in abstract_map:
            return abstract_map[old]
        original = next(
            (
                node
                for node in source_numbering.iter(qn("w:abstractNum"))
                if node.get(qn("w:abstractNumId")) == old
            ),
            None,
        )
        if original is None:
            raise ValueError(f"prototype abstract numbering {old} is missing")
        new = str(max(used_abstract, default=0) + 1)
        used_abstract.add(int(new))
        abstract_map[old] = new
        copied = deepcopy(original)
        copied.set(qn("w:abstractNumId"), new)
        first_definition = next(
            (
                i
                for i, node in enumerate(target_numbering)
                if node.tag in {qn("w:abstractNum"), qn("w:num")}
            ),
            len(target_numbering),
        )
        target_numbering.insert(first_definition, copied)
        for node in copied.iter():
            if node.tag in _STYLE_REFS and (value := node.get(qn("w:val"))):
                node.set(qn("w:val"), style(value))
        return new

    def num(old: str) -> str:
        if old in number_map:
            return number_map[old]
        original = next(
            (node for node in source_numbering.iter(qn("w:num")) if node.get(qn("w:numId")) == old),
            None,
        )
        if original is None:
            raise ValueError(f"prototype numbering {old} is missing")
        new = str(max(used_nums, default=0) + 1)
        used_nums.add(int(new))
        number_map[old] = new
        copied = deepcopy(original)
        copied.set(qn("w:numId"), new)
        abstract_id = copied.find(qn("w:abstractNumId"))
        if abstract_id is not None and (value := abstract_id.get(qn("w:val"))):
            abstract_id.set(qn("w:val"), abstract(value))
        cleanup = next(
            (i for i, node in enumerate(target_numbering) if node.tag == qn("w:numIdMacAtCleanup")),
            len(target_numbering),
        )
        target_numbering.insert(cleanup, copied)
        return new

    for element in elements:
        for node in element.iter():
            if node.tag in _STYLE_REFS and (value := node.get(qn("w:val"))):
                node.set(qn("w:val"), style(value))
            elif node.tag == qn("w:numId") and (value := node.get(qn("w:val"))):
                node.set(qn("w:val"), num(value))
