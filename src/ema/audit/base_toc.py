"""Keep audit heading numbers, TOC entries, and PAGEREF anchors aligned."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ema.audit.base_numbering import printed_numbers
from ema.audit.base_units import heading_spans_document
from ema.audit.catalogue import CATALOGUE
from ema.audit.heading_titles import normalize_body_heading, own_toc_title


def _text(paragraph: Any) -> str:
    return "".join(node.text or "" for node in paragraph.iter(qn("w:t")))


def _replace_leading_number(paragraph: Any, chapter: int) -> None:
    nodes = list(paragraph.iter(qn("w:t")))
    if not nodes:
        return
    text = _text(paragraph)
    match = re.match(r"^(\s*)(\d+)(?=[.\s-])", text)
    if match is None:
        return
    old = match.group(2)
    new = str(chapter)
    if old == new:
        return
    for node in nodes:
        value = node.text or ""
        if old in value:
            node.text = value.replace(old, new, 1)
            return
    nodes[0].text = text[: match.start(2)] + new + text[match.end(2) :]
    for node in nodes[1:]:
        node.text = ""


def _bookmark(paragraph: Any, name: str, number: int) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(number))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(number))
    paragraph.insert(1 if paragraph.find(qn("w:pPr")) is not None else 0, start)
    paragraph.append(end)


def _run(text: str, level: int = 2) -> Any:
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for name in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:" + name), "Times New Roman")
    properties.append(fonts)
    for name, value in (
        ("b", level == 1),
        ("i", level == 3),
        ("caps", False),
        ("smallCaps", False),
    ):
        node = OxmlElement("w:" + name)
        node.set(qn("w:val"), "1" if value else "0")
        properties.append(node)
    size = OxmlElement("w:sz")
    size.set(qn("w:val"), "24")
    properties.append(size)
    run.append(properties)
    if text:
        node = OxmlElement("w:t")
        node.text = text
        run.append(node)
    return run


def _toc_entry(prototype: Any, title: str, bookmark: str, number: str = "", level: int = 2) -> Any:
    entry: Any = OxmlElement("w:p")
    properties = prototype.find(qn("w:pPr"))
    if properties is not None:
        entry.append(deepcopy(properties))
    properties = entry.get_or_add_pPr()
    properties.get_or_add_pStyle().set(qn("w:val"), f"TOC{level}")
    indent = properties.get_or_add_ind()
    left = int(indent.get(qn("w:left"), "0")) - int(indent.get(qn("w:hanging"), "0"))
    offset = 600 if level == 1 else 1000
    indent.set(qn("w:left"), str(left + offset))
    indent.set(qn("w:hanging"), str(offset))
    indent.attrib.pop(qn("w:firstLine"), None)
    tabs = properties.get_or_add_tabs()
    for tab in list(tabs):
        if tab.get(qn("w:val")) != "right":
            tabs.remove(tab)
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "left")
    tab.set(qn("w:pos"), str(left + offset))
    tabs.insert(0, tab)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), bookmark)
    if number:
        hyperlink.append(_run(number, level))
        tab = _run("", level)
        tab.append(OxmlElement("w:tab"))
        hyperlink.append(tab)
    hyperlink.append(_run(title, level))
    tab = _run("", level)
    tab.append(OxmlElement("w:tab"))
    hyperlink.append(tab)
    entry.append(hyperlink)
    entry.append(_field_run("begin", level))
    instruction = _run("", level)
    code = OxmlElement("w:instrText")
    code.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    code.text = f" PAGEREF {bookmark} \\h "
    instruction.append(code)
    entry.append(instruction)
    entry.append(_field_run("separate", level))
    entry.append(_run("0", level))
    entry.append(_field_run("end", level))
    return entry


DEFAULT_TOC = ' TOC \\o "1-3" \\h \\z \\u '


def _field_run(kind: str, level: int = 1) -> Any:
    run = _run("", level)
    char = OxmlElement("w:fldChar")
    char.set(qn("w:fldCharType"), kind)
    run.append(char)
    return run


def _style(paragraph: Any) -> str:
    node = paragraph.find("./" + qn("w:pPr") + "/" + qn("w:pStyle"))
    return node.get(qn("w:val"), "") if node is not None else ""


def _take_toc_field(root: Any) -> tuple[list[Any], str]:  # noqa: C901
    """Select entries within the TOC field, preserving surrounding page breaks."""
    stack: list[tuple[bool, list[Any]]] = []
    entries: list[Any] = []
    instruction = DEFAULT_TOC
    for paragraph in root.findall(qn("w:p")):
        inside = any(toc for toc, _ in stack)
        for node in list(paragraph.iter(qn("w:fldChar"), qn("w:instrText"))):
            if node.tag == qn("w:instrText"):
                if stack and (node.text or "").strip().startswith("TOC"):
                    stack[-1] = (True, [*stack[-1][1], node])
                    inside = True
                    instruction = node.text or DEFAULT_TOC
                continue
            kind = node.get(qn("w:fldCharType"))
            if kind == "begin":
                stack.append((False, [node]))
            elif kind == "separate" and stack:
                stack[-1][1].append(node)
            elif kind == "end" and stack:
                toc, controls = stack.pop()
                if toc:
                    for control in (*controls, node):
                        control.getparent().remove(control)
        if inside and _style(paragraph).startswith("TOC"):
            entries.append(paragraph)
    return entries, instruction


def _wrap_in_field(entries: list[Any], instruction: str) -> None:
    """One TOC field around the entries, so Word can renumber them as its table of contents."""
    first = entries[0]
    properties = first.find(qn("w:pPr"))
    code = _run("", 1)
    text = OxmlElement("w:instrText")
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = instruction
    code.append(text)
    index = 1 if properties is not None else 0
    for offset, run in enumerate((_field_run("begin"), code, _field_run("separate"))):
        first.insert(index + offset, run)
    entries[-1].append(_field_run("end", int(_style(entries[-1])[-1])))


def _toc_prototypes(toc: list[Any], body: list[Any]) -> tuple[dict[int, Any], Any]:
    real = [
        element
        for element in toc
        if _text(element).strip()
        and not _text(element).startswith("Cuprins")
        and not element.xpath('.//w:br[@w:type="page"]')
    ]
    first = next(element for element in real if _style(element) == "TOC1")
    # A refreshed table may have only chapters, or only level-3 descendants.
    second = next((element for element in real if _style(element) in {"TOC2", "TOC3"}), first)
    prototypes = {1: first, 2: second}
    toc_heading = next(
        paragraph
        for paragraph in body
        if paragraph.tag == qn("w:p") and _text(paragraph).strip().upper() == "CUPRINS"
    )
    return prototypes, toc_heading


def _clear_bookmarks(document: Any) -> None:
    keep = {
        node.get(qn("w:id"))
        for node in document.element.iter(qn("w:bookmarkStart"))
        if (node.get(qn("w:name")) or "").startswith("_ema_")
    }
    for node in list(document.element.iter()):
        if (
            node.tag in (qn("w:bookmarkStart"), qn("w:bookmarkEnd"))
            and node.get(qn("w:id")) not in keep
        ):
            node.getparent().remove(node)


def refresh_toc(document: Any) -> None:
    root = document.element.body
    body = list(root)
    spans = heading_spans_document(document)
    has_measurements = any(item.section_id == "ch5" for item, _, _ in spans)
    for item, start, _ in spans:
        chapter = int(item.section_id[2])
        printed = chapter if has_measurements or chapter < 6 else chapter - 1
        _replace_leading_number(body[start], printed)
    _clear_bookmarks(document)
    body = list(root)
    toc, instruction = _take_toc_field(root)
    if not toc:
        raise ValueError("base has no TOC prototypes inside its TOC field")
    prototypes, toc_heading = _toc_prototypes(toc, body)
    numbers = printed_numbers(document)
    titles = {section.id: section.title for section in CATALOGUE}
    all_roots = [document.element]
    all_roots.extend(section.header._element for section in document.sections)
    all_roots.extend(section.footer._element for section in document.sections)
    all_ids = (
        int(node.get(qn("w:id"), "0"))
        for story in all_roots
        for node in story.iter(qn("w:bookmarkStart"))
    )
    number = max(all_ids, default=0) + 1
    bookmark = f"_Toc{number}"
    _bookmark(toc_heading, bookmark, number)
    entries = [_toc_entry(prototypes[1], "Cuprins", bookmark, level=1)]
    number += 1
    for item, start, _ in spans:
        heading = body[start]
        label = numbers.get(heading)
        if label is None:
            raise ValueError(f"heading has no printed number: {item.section_id}")
        level = len(label.rstrip(".").split("."))
        if level > 3:
            continue
        normalize_body_heading(heading, level)
        heading_text = re.sub(r"^\s*\d+(?:\.\d+)*[.\s-]+", "", _text(heading))
        title = heading_text.upper() if level == 1 else titles[item.section_id]
        if level > 1 and (item.section_id == "ch3.process" or "{" in title):
            title = own_toc_title(heading_text, item.template, titles[item.section_id])
        bookmark = f"_Toc{number}"
        _bookmark(heading, bookmark, number)
        entries.append(_toc_entry(prototypes[min(level, 2)], title, bookmark, label, level))
        number += 1
    previous = toc_heading
    for entry in entries:
        previous.addnext(entry)
        previous = entry
    for element in toc:
        if not element.xpath('.//w:br[@w:type="page"]'):
            root.remove(element)
    _wrap_in_field(entries, instruction)
