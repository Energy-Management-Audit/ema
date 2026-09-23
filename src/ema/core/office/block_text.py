"""Text replacement inside existing Word runs, including local missing markers."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
from itertools import pairwise

from lxml import etree

from ema.core.office.errors import OfficeError

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _red(node: etree._Element) -> None:
    for run in node.iter(f"{{{W}}}r"):
        props = run.find(f"{{{W}}}rPr")
        if props is None:
            props = etree.Element(f"{{{W}}}rPr")
            run.insert(0, props)
        colour = props.find(f"{{{W}}}color")
        if colour is None:
            colour = etree.SubElement(props, f"{{{W}}}color")
        colour.set(f"{{{W}}}val", "FF0000")


def _colour_missing(element: etree._Element, ranges: list[tuple[int, int]]) -> None:
    position = 0
    for node in list(element.iter(f"{{{W}}}t")):
        content = node.text or ""
        start, end = position, position + len(content)
        position = end
        cuts = {0, len(content)}
        for first, last in ranges:
            if first < end and last > start:
                cuts.update((max(0, first - start), min(len(content), last - start)))
        edges = sorted(cuts)
        if len(edges) == 2 and not any(first < end and last > start for first, last in ranges):
            continue
        run = node.getparent()
        if run is None or run.tag != f"{{{W}}}r" or len(run.findall(f"{{{W}}}t")) != 1:
            raise OfficeError("block_prototype", "Cannot colour a complex prototype run")
        parent = run.getparent()
        if parent is None:
            raise OfficeError("block_prototype", "Detached text run")
        offset = parent.index(run)
        for left, right in pairwise(edges):
            if left == right:
                continue
            clone = copy.deepcopy(run)
            clone_text = clone.find(f"{{{W}}}t")
            assert clone_text is not None
            clone_text.text = content[left:right]
            if any(first < start + right and last > start + left for first, last in ranges):
                _red(clone)
            parent.insert(offset, clone)
            offset += 1
        parent.remove(run)


def _slots(texts: list[etree._Element]) -> tuple[list[list[etree._Element]], list[bytes]]:
    slots: list[list[etree._Element]] = []
    keys: list[tuple[etree._Element, bytes]] = []
    for node in texts:
        run = node.getparent()
        if run is None or run.tag != f"{{{W}}}r":
            raise OfficeError("block_prototype", "Text is outside a run")
        paragraph = next(
            (parent for parent in run.iterancestors() if parent.tag == f"{{{W}}}p"), None
        )
        if paragraph is None:
            raise OfficeError("block_prototype", "Text run is outside a paragraph")
        props = run.find(f"{{{W}}}rPr")
        signature = (
            etree.tostring(props, method="c14n", exclusive=True) if props is not None else b""
        )
        key = (paragraph, signature)
        if not keys or key != keys[-1]:
            keys.append(key)
            slots.append([])
        slots[-1].append(node)
    return slots, [signature for _, signature in keys]


def _replacements(
    slots: list[list[etree._Element]], signatures: list[bytes], text: str, pieces: list[str] | None
) -> list[str]:
    original = ["".join(node.text or "" for node in slot) for slot in slots]
    rendered = pieces if pieces is not None else [text]
    if "".join(rendered) != text:
        raise ValueError("pieces must concatenate to text")
    if text == "".join(original):
        return original
    if len(slots) == 1:
        return [text]
    if len(rendered) == len(slots):
        return rendered
    layout = [(index, value, signatures[index].decode()) for index, value in enumerate(original)]
    raise OfficeError("mixed_run_replacement", f"paragraph slots: {layout}")


def set_text(
    element: etree._Element,
    text: str,
    *,
    missing: bool | list[tuple[int, int]] = False,
    pieces: list[str] | None = None,
) -> None:
    texts = list(element.iter(f"{{{W}}}t"))
    if not texts:
        if not text:
            return
        raise OfficeError("block_prototype", "Prototype has no text run")
    slots, signatures = _slots(texts)
    replacements = _replacements(slots, signatures, text, pieces)
    for slot, replacement in zip(slots, replacements, strict=True):
        remaining = replacement
        for node in slot[:-1]:
            length = len(node.text or "")
            node.text, remaining = remaining[:length], remaining[length:]
            node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        slot[-1].text = remaining
        slot[-1].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    if missing is True:
        _red(element)
    elif isinstance(missing, list) and missing:
        _colour_missing(element, missing)
