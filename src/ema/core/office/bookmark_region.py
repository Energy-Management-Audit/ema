"""Remove a region located by its bookmarked boundary paragraphs."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchors import AnchorLedger


def remove_following(first: etree._Element, last: etree._Element, ledger: AnchorLedger) -> None:
    """Remove siblings after the first paragraph through the last, recording their slots."""
    parent = first.getparent()
    if parent is None or parent is not last.getparent():
        raise ValueError("bookmarked region boundaries differ")
    children = list(parent)
    start, end = children.index(first), children.index(last)
    if start >= end:
        raise ValueError("bookmarked region boundaries reversed")
    for node in children[start + 1 : end + 1]:
        for bookmark in node.iter(qn("w:bookmarkStart")):
            name = bookmark.get(qn("w:name")) or ""
            if name.startswith("_ema_"):
                ledger.record(name.removeprefix("_ema_"), removed=True)
        parent.remove(node)
