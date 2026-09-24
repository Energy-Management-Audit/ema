"""Resolve non-paragraph Word targets through the shared hidden bookmarks."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import dataclass

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchors import find, stamp
from ema.core.office.package import REL_CHART, R, relationships, target_part, xml


@dataclass(frozen=True)
class RelationshipTarget:
    owner: str
    relationship_id: str
    part: str | None = None


def _parent(node: etree._Element, tag: str, slot: str) -> etree._Element:
    parents = list(node.iterancestors(tag))
    if len(parents) != 1:
        raise ValueError(f"anchor {slot} has no unique {tag} parent")
    return parents[0]


def stamp_cell(cell: etree._Element, slot: str, bookmark_id: int) -> None:
    paragraphs = cell.findall(qn("w:p"))
    if not paragraphs:
        raise ValueError(f"cell {slot} has no paragraph")
    stamp(paragraphs[0], slot, bookmark_id)


def stamp_row(row: etree._Element, slot: str, bookmark_id: int) -> None:
    cells = row.findall(qn("w:tc"))
    if not cells:
        raise ValueError(f"row {slot} has no cell")
    stamp_cell(cells[0], slot, bookmark_id)


def find_cell(roots: list[etree._Element], slot: str) -> etree._Element:
    return _parent(find(roots, slot), qn("w:tc"), slot)


def find_row(roots: list[etree._Element], slot: str) -> etree._Element:
    return _parent(find_cell(roots, slot), qn("w:tr"), slot)


def _owner(parts: dict[str, bytes], slot: str) -> tuple[str, etree._Element]:
    found: list[tuple[str, etree._Element]] = []
    for owner in parts:
        if not owner.startswith("word/") or not owner.endswith(".xml"):
            continue
        root = xml(parts, owner)
        if any(
            node.get(qn("w:name")) == f"_ema_{slot}" for node in root.iter(qn("w:bookmarkStart"))
        ):
            found.append((owner, find([root], slot)))
    if len(found) != 1:
        raise ValueError(f"expected one anchor {slot}, found {len(found)}")
    return found[0]


def chart_target(parts: dict[str, bytes], slot: str) -> RelationshipTarget:
    owner, paragraph = _owner(parts, slot)
    charts = [node for node in paragraph.iter() if node.tag.rsplit("}", 1)[-1] == "chart"]
    if len(charts) != 1:
        raise ValueError(f"anchor {slot} needs one chart")
    rid = charts[0].get(f"{{{R}}}id")
    matches = [
        rel
        for rel in relationships(parts, owner)
        if rel.get("Id") == rid and rel.get("Type") == REL_CHART
    ]
    if len(matches) != 1:
        raise ValueError(f"anchor {slot} has no unique chart relationship")
    return RelationshipTarget(owner, str(rid), target_part(owner, matches[0].get("Target", "")))


def hyperlink_target(parts: dict[str, bytes], slot: str) -> RelationshipTarget:
    owner, paragraph = _owner(parts, slot)
    links = list(paragraph.iter(qn("w:hyperlink")))
    ids = {node.get(f"{{{R}}}id") for node in links if node.get(f"{{{R}}}id")}
    if len(ids) != 1:
        raise ValueError(f"anchor {slot} needs one hyperlink")
    rid = next(iter(ids))
    matches = [
        rel
        for rel in relationships(parts, owner)
        if rel.get("Id") == rid and rel.get("Type", "").endswith("/hyperlink")
    ]
    if len(matches) != 1:
        raise ValueError(f"anchor {slot} has no unique hyperlink relationship")
    return RelationshipTarget(owner, str(rid))
