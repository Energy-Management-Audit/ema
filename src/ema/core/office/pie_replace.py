"""Replace a bookmarked PIEE pie picture with an editable native chart."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import posixpath

from lxml import etree

from ema.core.office.anchors import find
from ema.core.office.charts import _embed
from ema.core.office.package import (
    CT_CHART,
    REL_CHART,
    R,
    encoded,
    owner_part,
    rels_path,
    target_part,
    xml,
)
from ema.core.office.pie_xml import A, PieKind, pie_root

C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def _new_part(parts: dict[str, bytes]) -> str:
    return next(
        f"word/charts/chart{number}.xml"
        for number in range(1, 10000)
        if f"word/charts/chart{number}.xml" not in parts
    )


def _new_rid(root: etree._Element) -> str:
    used = {rel.get("Id") for rel in root}
    return next(f"rId{number}" for number in range(1, 10000) if f"rId{number}" not in used)


def _graphic(paragraph: etree._Element, slot: str) -> tuple[etree._Element, str]:
    blips = list(paragraph.iter(f"{{{A}}}blip"))
    if len(blips) != 1:
        raise ValueError(f"pie anchor {slot} does not enclose one picture")
    old_rid = blips[0].get(f"{{{R}}}embed")
    if old_rid is None:
        raise ValueError(f"pie anchor {slot} has no image relationship")
    graphics = list(paragraph.iter(f"{{{A}}}graphic"))
    if len(graphics) != 1:
        raise ValueError(f"pie anchor {slot} has no unique drawing graphic")
    return graphics[0], old_rid


def _replace_graphic(graphic: etree._Element, rid: str) -> None:
    for child in list(graphic):
        graphic.remove(child)
    content = etree.SubElement(graphic, f"{{{A}}}graphicData", uri=C)
    chart = etree.SubElement(content, f"{{{C}}}chart")
    chart.set(f"{{{R}}}id", rid)
    inline = next(
        graphic.iterancestors(
            "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}inline"
        ),
        None,
    )
    if inline is not None:
        for lock in inline.iter(
            "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}graphicFrameLocks"
        ):
            if "noChangeAspect" in lock.attrib:
                del lock.attrib["noChangeAspect"]


def _remove_unused_image(parts: dict[str, bytes], owner: str, old_rid: str) -> None:
    rel_path = rels_path(owner)
    rels = xml(parts, rel_path)
    old = next((item for item in rels if item.get("Id") == old_rid), None)
    if old is None or not old.get("Type", "").endswith("/image"):
        raise ValueError("pie picture relationship is missing")
    media = target_part(owner, old.get("Target", ""))
    rels.remove(old)
    parts[rel_path] = encoded(rels)
    used = any(
        target_part(owner_part(path), rel.get("Target", "")) == media
        for path in parts
        if path.endswith(".rels")
        for rel in xml(parts, path)
        if rel.get("TargetMode") != "External"
    )
    if not used:
        parts.pop(media, None)


def replace_pie_picture(
    parts: dict[str, bytes],
    slot: str,
    kind: PieKind,
    labels: tuple[str, ...],
    values: tuple[float, ...],
    *,
    representation: str = "normalized",
) -> str:
    """Keep the picture's exact inline size while changing it to a native 3D pie."""
    owner = "word/document.xml"
    document = xml(parts, owner)
    paragraph = find([document], slot)
    graphic, old_rid = _graphic(paragraph, slot)
    rel_path = rels_path(owner)
    rels = xml(parts, rel_path)
    rid = _new_rid(rels)
    chart_part = _new_part(parts)
    etree.SubElement(
        rels,
        f"{{{P}}}Relationship",
        Id=rid,
        Type=REL_CHART,
        Target=posixpath.relpath(chart_part, posixpath.dirname(owner)),
    )
    parts[rel_path] = encoded(rels)
    _replace_graphic(graphic, rid)
    parts[owner] = encoded(document)
    _remove_unused_image(parts, owner, old_rid)
    types = xml(parts, "[Content_Types].xml")
    etree.SubElement(types, f"{{{CT}}}Override", PartName="/" + chart_part, ContentType=CT_CHART)
    parts["[Content_Types].xml"] = encoded(types)
    _embed(parts, chart_part, pie_root(kind, labels, values, representation=representation))
    return chart_part


def remove_pie_picture(parts: dict[str, bytes], slot: str) -> None:
    owner = "word/document.xml"
    document = xml(parts, owner)
    paragraph = find([document], slot)
    _, old_rid = _graphic(paragraph, slot)
    parent = paragraph.getparent()
    if parent is None:
        raise ValueError("pie paragraph has no parent")
    parent.remove(paragraph)
    parts[owner] = encoded(document)
    _remove_unused_image(parts, owner, old_rid)
