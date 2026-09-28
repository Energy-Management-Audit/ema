"""Prune unused client assets and validate the resulting OOXML package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx.oxml.ns import qn
from lxml import etree

from ema.audit.base_numeric import approved_fixed_image
from ema.core.office.anchors import leftover_issues
from ema.core.office.package import (
    R,
    encoded,
    owner_part,
    read_parts,
    target_part,
    write_parts,
    xml,
)

_ASSETS = ("word/charts/", "word/media/", "word/embeddings/", "word/diagrams/", "word/activeX/")
_REL_ATTRS = {f"{{{R}}}{name}" for name in ("id", "embed", "link")}
_CONTENT_RELATIONS = ("/image", "/chart", "/oleObject", "/package", "/hyperlink")


def _used_ids(parts: dict[str, bytes], owner: str) -> set[str]:
    if owner not in parts or not owner.endswith(".xml"):
        return set()
    root = xml(parts, owner)
    return {
        str(value)
        for node in root.iter()
        for key, value in node.attrib.items()
        if key in _REL_ATTRS
    }


def _strip_ids(parts: dict[str, bytes], owner: str, ids: set[str]) -> None:
    if not ids or owner not in parts or not owner.endswith(".xml"):
        return
    root = xml(parts, owner)
    for node in root.iter():
        for key in _REL_ATTRS:
            if node.get(key) in ids:
                del node.attrib[key]
    parts[owner] = encoded(root)


def _prune_relationships(parts: dict[str, bytes]) -> None:
    for name in list(parts):
        if not name.endswith(".rels"):
            continue
        owner = owner_part(name)
        root = xml(parts, name)
        used = _used_ids(parts, owner)
        removed: set[str] = set()
        for relation in list(root):
            kind = relation.get("Type", "")
            target = relation.get("Target", "")
            unused_content = kind.endswith(_CONTENT_RELATIONS) and relation.get("Id") not in used
            if (
                relation.get("TargetMode") == "External"
                or target_part(owner, target) not in parts
                or unused_content
            ):
                removed.add(relation.get("Id", ""))
                root.remove(relation)
        parts[name] = encoded(root)
        _strip_ids(parts, owner, removed)


def _asset_references(parts: dict[str, bytes]) -> set[str]:
    return {
        target_part(owner_part(name), rel.get("Target", ""))
        for name in parts
        if name.endswith(".rels")
        for rel in xml(parts, name)
        if rel.get("TargetMode") != "External"
    }


def _rels_for(part: str) -> str:
    folder, _, name = part.rpartition("/")
    return f"{folder}/_rels/{name}.rels"


def scrub_package(path: Path) -> None:
    parts = {
        name: data for name, data in read_parts(path).items() if not name.startswith("docProps/")
    }
    _prune_relationships(parts)
    while True:
        referenced = _asset_references(parts)
        unused = [
            name
            for name in parts
            if name.startswith(_ASSETS) and not name.endswith(".rels") and name not in referenced
        ]
        if not unused:
            break
        for name in unused:
            parts.pop(name, None)
            parts.pop(_rels_for(name), None)
    _prune_relationships(parts)
    content_types = xml(parts, "[Content_Types].xml")
    for item in list(content_types):
        if item.tag.endswith("Override") and item.get("PartName", "").lstrip("/") not in parts:
            content_types.remove(item)
    parts["[Content_Types].xml"] = encoded(content_types)
    write_parts(parts, path)


def unreviewed_bullets(path: Path) -> list[str]:
    """Her numbering's picture bullets that no image digest approves; none may ship in a final."""
    parts = read_parts(path)
    rels = "word/_rels/numbering.xml.rels"
    if rels not in parts:
        return []
    targets = (
        target_part("word/numbering.xml", relation.get("Target", ""))
        for relation in xml(parts, rels)
        if relation.get("Type", "").endswith("/image")
    )
    return [
        f"unreviewed picture bullet: {name}"
        for name in targets
        if name not in parts or not approved_fixed_image(parts[name])
    ]


def _relationship_issues(parts: dict[str, bytes], name: str) -> list[str]:
    owner = owner_part(name)
    ids: set[str] = set()
    issues: list[str] = []
    for relation in xml(parts, name):
        rid = relation.get("Id", "")
        if rid in ids:
            issues.append(f"duplicate relationship ID: {name}")
        ids.add(rid)
        if relation.get("TargetMode") == "External":
            issues.append(f"external relationship: {name}")
        elif target_part(owner, relation.get("Target", "")) not in parts:
            issues.append(f"dangling relationship: {name}")
    for rid in _used_ids(parts, owner) - ids:
        issues.append(f"unresolved relationship ID in {owner}: {rid}")
    return issues


def _bookmark_issues(root: Any, name: str) -> list[str]:
    starts = [node.get(qn("w:id")) or "" for node in root.iter(qn("w:bookmarkStart"))]
    ends = [node.get(qn("w:id")) or "" for node in root.iter(qn("w:bookmarkEnd"))]
    issues: list[str] = []
    if len(starts) != len(set(starts)):
        issues.append(f"duplicate bookmark ID: {name}")
    if sorted(starts) != sorted(ends):
        issues.append(f"unpaired bookmarks: {name}")
    return issues


def _numeric_issues(root: Any, name: str, leftovers: tuple[str, ...]) -> list[str]:
    if not leftovers:
        return []
    for paragraph in root.iter(qn("w:p")):
        text = "".join(node.text or "" for node in paragraph.iter(qn("w:t"))).strip()
        if text in leftovers:
            return [f"numeric base paragraph remains in {name}"]
    return []


def _numbering_issues(root: Any) -> list[str]:
    order = {
        qn("w:numPicBullet"): 0,
        qn("w:abstractNum"): 1,
        qn("w:num"): 2,
        qn("w:numIdMacAtCleanup"): 3,
    }
    positions = [order[node.tag] for node in root if node.tag in order]
    return ["invalid numbering element order"] if positions != sorted(positions) else []


def package_issues(  # noqa: C901
    path: Path, denylist: tuple[str, ...], *, numeric_leftovers: tuple[str, ...] = ()
) -> list[str]:
    parts = read_parts(path)
    issues: list[str] = []
    references = _asset_references(parts)
    bookmark_ids: set[str] = set()
    for name, data in parts.items():
        if name.startswith(_ASSETS) and (
            owner_part(name) not in parts if name.endswith(".rels") else name not in references
        ):
            issues.append(f"orphan asset: {name}")
        if name.endswith(".rels"):
            issues.extend(_relationship_issues(parts, name))
        if name.endswith((".xml", ".rels")):
            root = etree.fromstring(data)
            if name == "word/numbering.xml":
                issues.extend(_numbering_issues(root))
            if name.startswith("word/") and name.endswith(".xml"):
                issues.extend(_bookmark_issues(root, name))
                issues.extend(_numeric_issues(root, name, numeric_leftovers))
                for blip in root.iter(qn("a:blip")):
                    if not (blip.get(f"{{{R}}}embed") or blip.get(f"{{{R}}}link")):
                        issues.append(f"image without relationship in {name}")
                for bookmark in root.iter(qn("w:bookmarkStart")):
                    number = bookmark.get(qn("w:id"), "")
                    if number in bookmark_ids:
                        issues.append("duplicate bookmark ID across stories")
                    bookmark_ids.add(number)
    issues.extend(f"base identity remains in {name}" for name in leftover_issues(path, denylist))
    return sorted(set(issues))
