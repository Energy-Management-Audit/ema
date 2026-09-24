"""Versioned local classification and stamping of a Word base document."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchor_targets import stamp_cell, stamp_row
from ema.core.office.anchors import stamp
from ema.core.office.package import encoded, read_parts, write_parts, xml

Kind = Literal[
    "paragraph",
    "cell",
    "row",
    "chart",
    "picture",
    "hyperlink",
    "chart_part",
    "relationship",
    "property",
]
STAMPABLE = frozenset({"paragraph", "cell", "row", "chart", "picture", "hyperlink"})


@dataclass(frozen=True)
class BaseElement:
    id: str
    kind: Kind
    owner: str
    selector: str
    classification: Literal["fixed", "variable"]
    slot: str | None = None


@dataclass(frozen=True)
class BaseMap:
    base_sha: str
    elements: tuple[BaseElement, ...]

    @property
    def variable_slots(self) -> frozenset[str]:
        return frozenset(e.slot for e in self.elements if e.slot is not None)


def _id(kind: Kind, owner: str, selector: str) -> str:
    return f"{kind}:{owner}:{selector}"


def _xml_items(parts: dict[str, bytes]) -> list[tuple[Kind, str, str]]:
    items: list[tuple[Kind, str, str]] = []
    tags: dict[str, Kind] = {
        qn("w:p"): "paragraph",
        qn("w:tc"): "cell",
        qn("w:tr"): "row",
        qn("w:hyperlink"): "hyperlink",
        "{http://schemas.openxmlformats.org/drawingml/2006/chart}chart": "chart",
        "{http://schemas.openxmlformats.org/drawingml/2006/main}blip": "picture",
    }
    for owner in sorted(parts):
        if owner.startswith("word/charts/") and owner.endswith(".xml"):
            items.append(("chart_part", owner, "/"))
        if owner.endswith(".rels"):
            root = xml(parts, owner)
            items.extend(("relationship", owner, rel.get("Id", "")) for rel in root)
        if owner in {"docProps/core.xml", "docProps/app.xml"}:
            root = xml(parts, owner)
            items.extend(
                ("property", owner, root.getroottree().getelementpath(child)) for child in root
            )
        if not owner.startswith("word/") or not owner.endswith(".xml"):
            continue
        if owner.startswith(("word/charts/", "word/theme/", "word/styles")):
            continue
        root = xml(parts, owner)
        for node in root.iter():
            kind = tags.get(node.tag)
            if kind is not None:
                items.append((kind, owner, root.getroottree().getelementpath(node)))
    return items


def inventory(base: Path) -> tuple[BaseElement, ...]:
    """Enumerate every contract surface without returning any client content."""
    return tuple(
        BaseElement(_id(kind, owner, selector), kind, owner, selector, "fixed")
        for kind, owner, selector in _xml_items(read_parts(base))
    )


def classify(base: Path, variable: dict[str, str]) -> BaseMap:
    """Materialize an explicit fixed/variable record for every base element."""
    elements = inventory(base)
    unknown = set(variable) - {element.id for element in elements}
    if unknown:
        raise ValueError(f"unknown base element ids: {len(unknown)}")
    mapped = tuple(
        BaseElement(
            e.id,
            e.kind,
            e.owner,
            e.selector,
            "variable" if e.id in variable else "fixed",
            variable.get(e.id),
        )
        for e in elements
    )
    if any(e.classification == "variable" and not e.slot for e in mapped):
        raise ValueError("variable base element needs a slot")
    return BaseMap(hashlib.sha256(base.read_bytes()).hexdigest(), mapped)


def validate(base: Path, mapping: BaseMap) -> None:
    if mapping.base_sha != hashlib.sha256(base.read_bytes()).hexdigest():
        raise ValueError("base hash differs from its anchor map")
    expected = {e.id for e in inventory(base)}
    classified = {e.id for e in mapping.elements}
    if expected != classified or len(classified) != len(mapping.elements):
        raise ValueError("base anchor map has unclassified or duplicate elements")
    if any(e.classification == "variable" and not e.slot for e in mapping.elements):
        raise ValueError("variable base element needs a slot")
    stamped = {
        e.slot for e in mapping.elements if e.classification == "variable" and e.kind in STAMPABLE
    }
    unsupported = mapping.variable_slots - stamped
    if unsupported:
        raise ValueError(f"variable package targets need a bookmark companion: {len(unsupported)}")


def save(mapping: BaseMap, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"base_sha": mapping.base_sha, "elements": [asdict(e) for e in mapping.elements]},
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def load(path: Path) -> BaseMap:
    value = json.loads(path.read_text(encoding="utf-8"))
    return BaseMap(value["base_sha"], tuple(BaseElement(**e) for e in value["elements"]))


def _target(root: etree._Element, entry: BaseElement) -> etree._Element:
    node = root.find(entry.selector)
    if node is None:
        raise ValueError(f"base target not unique: {entry.id}")
    return node


def _paragraph(node: etree._Element) -> etree._Element:
    if node.tag == qn("w:p"):
        return node
    parents = list(node.iterancestors(qn("w:p")))
    if len(parents) != 1:
        raise ValueError("variable drawing or hyperlink needs one paragraph")
    return parents[0]


def _preview_label(paragraph: etree._Element, slot: str) -> None:
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    colour = OxmlElement("w:color")
    colour.set(qn("w:val"), "FF0000")
    properties.append(colour)
    run.append(properties)
    label = OxmlElement("w:t")
    label.text = f" [{slot}]"
    run.append(label)
    paragraph.append(run)


def stamp_base(base: Path, mapping: BaseMap, output: Path, *, preview: bool = False) -> None:
    """Write a local stamped copy; runtime generation later resolves only bookmarks."""
    validate(base, mapping)
    parts = read_parts(base)
    roots: dict[str, etree._Element] = {}
    bookmark_id = 1
    stamped: set[str] = set()
    for entry in mapping.elements:
        if entry.classification != "variable" or entry.kind not in STAMPABLE:
            continue
        assert entry.slot is not None
        if entry.slot in stamped:
            continue
        root = roots.setdefault(entry.owner, xml(parts, entry.owner))
        node = _target(root, entry)
        if entry.kind == "cell":
            stamp_cell(node, entry.slot, bookmark_id)
        elif entry.kind == "row":
            stamp_row(node, entry.slot, bookmark_id)
        else:
            stamp(_paragraph(node), entry.slot, bookmark_id)
        if preview:
            paragraph = (
                node.find(qn("w:p"))
                if entry.kind == "cell"
                else node.find(f"{qn('w:tc')}/{qn('w:p')}")
                if entry.kind == "row"
                else _paragraph(node)
            )
            if paragraph is None:
                raise ValueError(f"cannot preview slot {entry.slot}")
            _preview_label(paragraph, entry.slot)
        bookmark_id += 1
        stamped.add(entry.slot)
    parts.update({owner: encoded(root) for owner, root in roots.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    write_parts(parts, output)
