"""Read the labels Word prints, including the base's literal-prefix lists."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _paragraph_properties(paragraph: Any, styles: dict[str, Any]) -> list[Any]:
    properties = paragraph.find(qn("w:pPr"))
    style_node = properties.find(qn("w:pStyle")) if properties is not None else None
    style_id = str(style_node.get(qn("w:val"), "")) if style_node is not None else ""
    style = styles.get(style_id)
    chain = [properties]
    seen: set[str] = set()
    while style is not None and style.style_id not in seen:
        seen.add(style.style_id)
        chain.append(style.element.pPr)
        style = style.base_style
    return chain


def _num_properties(paragraph: Any, styles: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for properties in _paragraph_properties(paragraph, styles):
        numpr = properties.find(qn("w:numPr")) if properties is not None else None
        if numpr is not None:
            for child in numpr:
                result.setdefault(child.tag, child.get(qn("w:val"), "0"))
    return result


def effective_indent(document: Any, paragraph: Any) -> tuple[int, int]:
    """Resolve list-level, style and direct indents; return left and hanging in twips."""
    styles = {style.style_id: style for style in document.styles}
    chain = _paragraph_properties(paragraph, styles)
    numbering = document.part.numbering_part.element
    numpr = _num_properties(paragraph, styles)
    num_id = numpr.get(qn("w:numId"), "0")
    index = numpr.get(qn("w:ilvl"), "0")
    num = numbering.find(f'./{qn("w:num")}[@{qn("w:numId")}="{num_id}"]')
    definition = None
    if num is not None and num_id != "0":
        override = num.find(f'./{qn("w:lvlOverride")}[@{qn("w:ilvl")}="{index}"]')
        definition = override.find(qn("w:lvl")) if override is not None else None
        if definition is None:
            abstract_id = _value(num, "w:abstractNumId", "0")
            abstract = numbering.find(
                f'./{qn("w:abstractNum")}[@{qn("w:abstractNumId")}="{abstract_id}"]'
            )
            if abstract is not None:
                definition = abstract.find(f'./{qn("w:lvl")}[@{qn("w:ilvl")}="{index}"]')
    ordered: list[Any] = []
    if definition is not None:
        ordered.append(definition.find(qn("w:pPr")))
    ordered.extend(reversed(chain[1:]))
    ordered.append(chain[0])
    left, hanging = 0, 0
    for properties in ordered:
        indent = properties.find(qn("w:ind")) if properties is not None else None
        if indent is not None:
            left = int(indent.get(qn("w:left"), str(left)))
            if qn("w:hanging") in indent.attrib:
                hanging = int(indent.get(qn("w:hanging")))
            elif qn("w:firstLine") in indent.attrib:
                hanging = -int(indent.get(qn("w:firstLine")))
    return left, hanging


def _value(element: Any, name: str, default: str) -> str:
    node = element.find(qn(name)) if element is not None else None
    return node.get(qn("w:val"), default) if node is not None else default


def _levels(numbering: Any, num: Any) -> dict[int, tuple[str, int, int]]:
    abstract_id = _value(num, "w:abstractNumId", "0")
    abstract = numbering.find(f'./{qn("w:abstractNum")}[@{qn("w:abstractNumId")}="{abstract_id}"]')
    result: dict[int, tuple[str, int, int]] = {}
    if abstract is None:
        raise ValueError("heading numbering has no abstract list")
    for level in abstract.findall(qn("w:lvl")):
        index = int(level.get(qn("w:ilvl"), "0"))
        override = num.find(f'./{qn("w:lvlOverride")}[@{qn("w:ilvl")}="{index}"]')
        definition = override.find(qn("w:lvl")) if override is not None else None
        definition = level if definition is None else definition
        start = int(_value(override, "w:startOverride", _value(definition, "w:start", "1")))
        result[index] = (
            _value(definition, "w:lvlText", ""),
            start,
            int(_value(definition, "w:lvlRestart", str(index))),
        )
    return result


def printed_numbers(document: Any) -> dict[Any, str]:
    """Evaluate list counters in body order; explicit typed labels remain explicit."""
    styles = {style.style_id: style for style in document.styles}
    numbering = document.part.numbering_part.element
    lists = {
        node.get(qn("w:numId")): _levels(numbering, node) for node in numbering.findall(qn("w:num"))
    }
    counters: dict[str, dict[int, int]] = {}
    result: dict[Any, str] = {}
    for paragraph in document.element.body.iter(qn("w:p")):
        properties = paragraph.find(qn("w:pPr"))
        style = _value(properties, "w:pStyle", "")
        if style.startswith("TOC"):
            continue
        numpr = _num_properties(paragraph, styles)
        num_id = numpr.get(qn("w:numId"), "0")
        if num_id == "0" or num_id not in lists:
            text = "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
            if match := re.match(r"^\s*(\d+(?:\.\d+)*\.)\s", text):
                result[paragraph] = match.group(1)
            continue
        level = int(numpr.get(qn("w:ilvl"), "0"))
        definitions = lists[num_id]
        if level not in definitions:
            continue
        pattern, start, _ = definitions[level]
        values = counters.setdefault(num_id, {})
        values[level] = values.get(level, start - 1) + 1
        for deeper, (_, _, restart) in definitions.items():
            if deeper > level and restart and level <= restart - 1:
                values.pop(deeper, None)
        result[paragraph] = re.sub(
            r"%(\d)",
            lambda match, values=values, definitions=definitions: str(
                values.get(int(match[1]) - 1, definitions[int(match[1]) - 1][1])
            ),
            pattern,
        )
    return result


def insert_chapter_numbering(document: Any, inserted: Any, following: list[Any]) -> None:
    """Join an imported chapter to the base list and shift the following literal prefixes."""
    styles = {style.style_id: style for style in document.styles}
    properties = _num_properties(following[0], styles)
    num_id = properties.get(qn("w:numId"))
    if num_id is None:
        raise ValueError("base chapter has no numbering prototype")
    numpr = inserted.get_or_add_pPr().get_or_add_numPr()
    numpr.get_or_add_numId().val = int(num_id)
    numpr.get_or_add_ilvl().val = int(properties.get(qn("w:ilvl"), "0"))
    numbering = document.part.numbering_part.element
    shifted: set[tuple[str, int]] = set()
    for paragraph in following[1:]:
        properties = _num_properties(paragraph, styles)
        num_id = properties.get(qn("w:numId"), "0")
        index = int(properties.get(qn("w:ilvl"), "0"))
        if num_id == "0" or (num_id, index) in shifted:
            continue
        shifted.add((num_id, index))
        num = numbering.find(f'./{qn("w:num")}[@{qn("w:numId")}="{num_id}"]')
        abstract_id = _value(num, "w:abstractNumId", "0")
        abstract = numbering.find(
            f'./{qn("w:abstractNum")}[@{qn("w:abstractNumId")}="{abstract_id}"]'
        )
        override = num.find(f'./{qn("w:lvlOverride")}[@{qn("w:ilvl")}="{index}"]')
        definition = override.find(qn("w:lvl")) if override is not None else None
        if definition is None:
            definition = abstract.find(f'./{qn("w:lvl")}[@{qn("w:ilvl")}="{index}"]')
        pattern = _value(definition, "w:lvlText", "")
        match = re.match(r"^(\d+)\.", pattern)
        if match is None:
            continue
        if override is None:
            override = OxmlElement("w:lvlOverride")
            override.set(qn("w:ilvl"), str(index))
            num.append(override)
        elif definition.getparent() is override:
            override.remove(definition)
        copied = deepcopy(definition)
        copied.find(qn("w:lvlText")).set(
            qn("w:val"), str(int(match[1]) + 1) + pattern[len(match[1]) :]
        )
        override.append(copied)
