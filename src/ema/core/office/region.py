"""Replace a document body region and retire its unused chart resources."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from lxml import etree

from ema.core.office.blocks import Block, ElementLocator, Prototypes, RenderReport, render
from ema.core.office.errors import OfficeError
from ema.core.office.package import (
    REL_CHART,
    C,
    R,
    encoded,
    read_parts,
    rels_path,
    target_part,
    write_parts,
    xml,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def _body(parts: dict[str, bytes]) -> tuple[etree._Element, etree._Element]:
    root = xml(parts, "word/document.xml")
    body = root.find(f"{{{W}}}body")
    if body is None:
        raise OfficeError("block_prototype", "Document body is missing")
    return root, body


def _chart_ids(nodes: list[etree._Element]) -> Counter[str]:
    return Counter(
        rid
        for node in nodes
        for chart in node.iter(f"{{{C}}}chart")
        if (rid := chart.get(f"{{{R}}}id"))
    )


def _retire_unreferenced(parts: dict[str, bytes], candidates: set[str]) -> None:
    """Remove a chart resource only after all package relationships stop referring to it."""
    removed: set[str] = set()
    while candidates:
        referenced = {
            target_part(owner, rel.get("Target", ""))
            for owner in parts
            if owner.endswith(".xml") and rels_path(owner) in parts
            for rel in xml(parts, rels_path(owner))
            if rel.get("TargetMode") != "External"
        }
        disposable = {part for part in candidates if part not in referenced and part in parts}
        if not disposable:
            break
        candidates -= disposable
        for part in disposable:
            path = rels_path(part)
            if path in parts:
                for rel in xml(parts, path):
                    if rel.get("TargetMode") != "External":
                        candidates.add(target_part(part, rel.get("Target", "")))
                del parts[path]
            del parts[part]
        removed.update(disposable)
    if removed:
        types = xml(parts, "[Content_Types].xml")
        for override in list(types):
            if (
                override.tag == f"{{{CT}}}Override"
                and override.get("PartName", "").lstrip("/") in removed
            ):
                types.remove(override)
        parts["[Content_Types].xml"] = encoded(types)


def _remove_old_charts(parts: dict[str, bytes], old: list[etree._Element]) -> None:
    root, body = _body(parts)
    old_ids = _chart_ids(old)
    remaining = _chart_ids(list(body))
    path = rels_path("word/document.xml")
    rels = xml(parts, path)
    candidates: set[str] = set()
    for rel in list(rels):
        rid = rel.get("Id", "")
        if rel.get("Type") != REL_CHART or rid not in old_ids or rid in remaining:
            continue
        candidates.add(target_part("word/document.xml", rel.get("Target", "")))
        rels.remove(rel)
    parts[path] = encoded(rels)
    parts["word/document.xml"] = encoded(root)
    _retire_unreferenced(parts, candidates)


def replace_region(  # noqa: PLR0913
    docx: Path,
    out: Path,
    start: ElementLocator,
    end: ElementLocator,
    blocks: list[Block],
    prototypes: Prototypes,
    *,
    keep_old: set[int] | None = None,
) -> RenderReport:
    """Replace exclusive body children between two stable, prelocated anchor elements."""
    original = read_parts(docx)
    _, body = _body(original)
    if not 1 <= start.body_index < end.body_index <= len(body) - 1:
        raise OfficeError("block_prototype", "Invalid region anchors")
    with TemporaryDirectory() as directory:
        rendered = Path(directory) / "rendered.docx"
        report = render(docx, rendered, start, blocks, prototypes, allow_retained=True)
        parts = read_parts(rendered)
    root, replacement_body = _body(parts)
    added = len(replacement_body) - len(body)
    if added < 0:
        raise OfficeError("block_prototype", "Rendering unexpectedly removed body content")
    old = list(replacement_body)[start.body_index + added : end.body_index + added - 1]
    for index, node in enumerate(old):
        if keep_old is None or index not in keep_old:
            replacement_body.remove(node)
    parts["word/document.xml"] = encoded(root)
    _remove_old_charts(parts, old)
    write_parts(parts, out)
    return report
