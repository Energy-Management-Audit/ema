"""Copy the auditor's fixed chapter-five paragraphs by mapped heading labels."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from docx import Document
from lxml import etree

from ema.audit.base_prototypes import import_formatting
from ema.audit.base_units import heading_spans_document

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _text(element: etree._Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t"))


def fixed_elements(  # noqa: C901
    target: Any,
    prototype: Path,
    identities: tuple[str, ...],
    required: frozenset[str],
    *,
    digest_changes: list[str] | None = None,
) -> tuple[dict[str, etree._Element], dict[str, list[str]], list[str]]:
    source = Document(str(prototype))
    positions = {item.section_id: start for item, start, _ in heading_spans_document(source)}
    body = list(cast(etree._Element, cast(Any, source.element).body))
    sections = {
        "method": ("ch5.electric", "ch5.electric_fisa", 1),
        "harmonics": ("ch5.electric_concluzii", "ch5.termic", 2),
        "thermal": ("ch5.termic", "ch5.termic_fisa", 1),
    }
    elements: dict[str, etree._Element] = {}
    keys: dict[str, list[str]] = {}
    issues: list[str] = []
    for name, (first, last, offset) in sections.items():
        if name not in required:
            continue
        start, end = positions.get(first), positions.get(last)
        if start is None or end is None or start + offset >= end:
            issues.append(f"fixed {name} heading or range missing in measurement prototype")
            continue
        selected = body[start + offset : end]
        if name == "method":
            instrument = next(
                (
                    index
                    for index, node in enumerate(selected)
                    if _text(node).strip().startswith("Pentru realizarea măsurătorilor electrice")
                ),
                None,
            )
            if instrument is None:
                issues.append("fixed method instrument label missing in measurement prototype")
                continue
            selected = selected[:instrument]
        if name == "harmonics":
            selected = [
                node
                for node in selected
                if not any(term.casefold() in _text(node).casefold() for term in identities)
            ]
        selected = [node for node in selected if node.tag in {W + "p", W + "tbl"}]
        if not any(_text(node).strip() for node in selected):
            issues.append(f"fixed {name} text missing in measurement prototype")
            continue
        copies = [deepcopy(node) for node in selected]
        import_formatting(target, source, copies)
        for copy in copies:
            before = _text(copy)
            for node in copy.iter(W + "t"):
                node.text = (node.text or "").translate(str.maketrans("şţŞŢ", "șțȘȚ"))
            after = _text(copy)
            if before != after and digest_changes is not None:
                digest_changes.append(
                    f"F17 ch5 {name} fixed text: "
                    f"{hashlib.sha256(before.encode()).hexdigest()} → "
                    f"{hashlib.sha256(after.encode()).hexdigest()}"
                )
            for blip in copy.iter(A + "blip"):
                relationship = blip.get(R + "embed")
                if relationship is not None:
                    image = source.part.related_parts[relationship]
                    replacement, _ = target.part.get_or_add_image(BytesIO(image.blob))
                    blip.set(R + "embed", replacement)
        keys[name] = [f"fixed:{name}:{index}" for index in range(len(copies))]
        elements.update(zip(keys[name], copies, strict=True))
    return elements, keys, issues
