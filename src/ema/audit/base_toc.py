"""Keep audit heading numbers, TOC entries, and PAGEREF anchors aligned."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ema.audit.base_units import heading_spans_document


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


def _run(text: str) -> Any:
    run = OxmlElement("w:r")
    node = OxmlElement("w:t")
    node.text = text
    run.append(node)
    return run


def _toc_entry(prototype: Any, title: str, bookmark: str) -> Any:
    entry = OxmlElement("w:p")
    properties = prototype.find(qn("w:pPr"))
    if properties is not None:
        entry.append(deepcopy(properties))
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), bookmark)
    hyperlink.append(_run(title))
    tab = OxmlElement("w:r")
    tab.append(OxmlElement("w:tab"))
    hyperlink.append(tab)
    entry.append(hyperlink)
    field_start = OxmlElement("w:r")
    char = OxmlElement("w:fldChar")
    char.set(qn("w:fldCharType"), "begin")
    field_start.append(char)
    entry.append(field_start)
    instruction = OxmlElement("w:r")
    code = OxmlElement("w:instrText")
    code.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    code.text = f" PAGEREF {bookmark} \\h "
    instruction.append(code)
    entry.append(instruction)
    separator = OxmlElement("w:r")
    char = OxmlElement("w:fldChar")
    char.set(qn("w:fldCharType"), "separate")
    separator.append(char)
    entry.append(separator)
    entry.append(_run("0"))
    field_end = OxmlElement("w:r")
    char = OxmlElement("w:fldChar")
    char.set(qn("w:fldCharType"), "end")
    field_end.append(char)
    entry.append(field_end)
    return entry


DEFAULT_TOC = ' TOC \\o "1-2" \\h \\z \\u '


def _field_run(kind: str) -> Any:
    run = OxmlElement("w:r")
    char = OxmlElement("w:fldChar")
    char.set(qn("w:fldCharType"), kind)
    run.append(char)
    return run


def _take_toc_field(root: Any, toc: list[Any]) -> str:
    """Return the base's TOC instruction and drop a field end left outside the TOC entries."""
    instruction = DEFAULT_TOC
    stack: list[bool] = []
    entries = set(toc)
    orphans: list[Any] = []
    for node in root.iter(qn("w:fldChar"), qn("w:instrText")):
        if node.tag == qn("w:instrText"):
            if stack and not stack[-1] and (node.text or "").strip().startswith("TOC"):
                stack[-1] = True
                instruction = node.text or DEFAULT_TOC
            continue
        kind = node.get(qn("w:fldCharType"))
        if kind == "begin":
            stack.append(False)
        elif kind == "end" and stack and stack.pop():
            paragraph = next(node.iterancestors(qn("w:p")), None)
            if paragraph is not None and paragraph not in entries:
                orphans.append(node.getparent())
    for run in orphans:
        run.getparent().remove(run)
    return instruction


def _wrap_in_field(entries: list[Any], instruction: str) -> None:
    """One TOC field around the entries, so Word can renumber them as its table of contents."""
    first = entries[0]
    properties = first.find(qn("w:pPr"))
    code = OxmlElement("w:r")
    text = OxmlElement("w:instrText")
    text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = instruction
    code.append(text)
    index = 1 if properties is not None else 0
    for offset, run in enumerate((_field_run("begin"), code, _field_run("separate"))):
        first.insert(index + offset, run)
    entries[-1].append(_field_run("end"))


def refresh_toc(document: Any) -> None:
    root = document.element.body
    body = list(root)
    spans = heading_spans_document(document)
    has_measurements = any(item.section_id == "ch5" for item, _, _ in spans)
    for item, start, _ in spans:
        chapter = int(item.section_id[2])
        printed = chapter if has_measurements or chapter < 6 else chapter - 1
        _replace_leading_number(body[start], printed)
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
    body = list(root)
    toc = [
        element
        for element in body
        if element.tag == qn("w:p")
        and (style := element.find("./" + qn("w:pPr") + "/" + qn("w:pStyle"))) is not None
        and (style.get(qn("w:val")) or "") in {"TOC1", "TOC2"}
    ]
    if not toc:
        raise ValueError("base has no TOC prototypes")
    prototypes = {
        level: next(
            element
            for element in toc
            if element.find("./" + qn("w:pPr") + "/" + qn("w:pStyle")).get(qn("w:val"))
            == f"TOC{level}"
        )
        for level in (1, 2)
    }
    instruction = _take_toc_field(root, toc)
    before = toc[0]
    all_roots = [document.element]
    all_roots.extend(section.header._element for section in document.sections)
    all_roots.extend(section.footer._element for section in document.sections)
    all_ids = (
        int(node.get(qn("w:id"), "0"))
        for story in all_roots
        for node in story.iter(qn("w:bookmarkStart"))
    )
    number = max(all_ids, default=0) + 1
    subsection: dict[int, int] = {}
    entries: list[Any] = []
    for item, start, _ in spans:
        if item.heading.level not in (0, 1):
            continue
        chapter = int(item.section_id[2])
        printed = chapter if has_measurements or chapter < 6 else chapter - 1
        heading_text = re.sub(r"^\s*\d+(?:\.\d+)*[.\s-]+", "", _text(body[start]))
        if item.heading.level == 0:
            subsection[chapter] = 0
            title = f"{printed}. {heading_text}"
        else:
            subsection[chapter] = subsection.get(chapter, 0) + 1
            title = f"{printed}.{subsection[chapter]}. {heading_text}"
        bookmark = f"_Toc{number}"
        _bookmark(body[start], bookmark, number)
        entry = _toc_entry(prototypes[item.heading.level + 1], title, bookmark)
        before.addprevious(entry)
        entries.append(entry)
        number += 1
    for element in toc:
        root.remove(element)
    if entries:
        _wrap_in_field(entries, instruction)
