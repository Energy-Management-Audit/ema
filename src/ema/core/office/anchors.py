"""Bookmark-addressed document slots and package-wide identity checks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.package import read_parts

PREFIX = "_ema_"


def _empty_slots() -> set[str]:
    return set()


def stamp(paragraph: Any, slot: str, bookmark_id: int) -> None:
    """Place a hidden bookmark around a paragraph's variable content."""
    if not slot or any(char.isspace() for char in slot):
        raise ValueError("slot must be a nonempty bookmark token")
    if bookmark_id < 0:
        raise ValueError("bookmark_id must be nonnegative")
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), PREFIX + slot)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    paragraph.insert(1 if paragraph.find(qn("w:pPr")) is not None else 0, start)
    paragraph.append(end)


def find(roots: Iterable[Any], slot: str) -> Any:
    """Find a variable paragraph by bookmark name, never by text or index."""
    name = PREFIX + slot
    matches = [
        node
        for root in roots
        for node in root.iter(qn("w:bookmarkStart"))
        if node.get(qn("w:name")) == name
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one anchor {slot}, found {len(matches)}")
    paragraph = matches[0].getparent()
    if paragraph is None or paragraph.tag != qn("w:p"):
        raise ValueError(f"anchor {slot} is not in a paragraph")
    return paragraph


@dataclass
class AnchorLedger:
    expected: frozenset[str]
    written: set[str] = field(default_factory=_empty_slots)
    removed: set[str] = field(default_factory=_empty_slots)

    def record(self, slot: str, *, removed: bool = False) -> None:
        if slot not in self.expected:
            raise ValueError(f"unknown anchor {slot}")
        (self.removed if removed else self.written).add(slot)

    @property
    def untouched(self) -> frozenset[str]:
        return self.expected - self.written - self.removed


def strip(roots: Iterable[Any]) -> int:
    """Remove only Ema bookmarks after all slots have been resolved."""
    removed = 0
    for root in roots:
        ids = {
            node.get(qn("w:id"))
            for node in root.iter(qn("w:bookmarkStart"))
            if (node.get(qn("w:name")) or "").startswith(PREFIX)
        }
        for node in list(root.iter()):
            if (
                node.tag in {qn("w:bookmarkStart"), qn("w:bookmarkEnd")}
                and node.get(qn("w:id")) in ids
            ):
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
                    removed += 1
    return removed


def _embedded_contains(data: bytes, terms: tuple[str, ...]) -> bool:
    try:
        with ZipFile(BytesIO(data)) as workbook:
            return any(
                term.casefold() in workbook.read(name).decode("utf-8", errors="ignore").casefold()
                for name in workbook.namelist()
                if name.endswith((".xml", ".rels"))
                for term in terms
            )
    except BadZipFile:
        return any(
            term.casefold() in data.decode("utf-8", errors="ignore").casefold() for term in terms
        )


def leftover_issues(path: Path, denylist: tuple[str, ...]) -> list[str]:
    """Scan package XML, relationships and embedded workbooks for local identity terms."""
    if not denylist or any(not term.strip() for term in denylist):
        raise ValueError("a nonempty identity denylist is required")
    issues: list[str] = []
    for name, data in read_parts(path).items():
        if name.startswith("word/embeddings/"):
            if _embedded_contains(data, denylist):
                issues.append(name)
        elif name.endswith((".xml", ".rels")):
            root = etree.fromstring(data)
            content = etree.tostring(root, encoding="unicode").casefold()
            if any(term.casefold() in content for term in denylist):
                issues.append(name)
    return sorted(set(issues))
