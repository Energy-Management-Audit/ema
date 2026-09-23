"""Fresh OOXML identifiers for cloned chart drawings."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import re
import secrets
import uuid

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _word_paragraph_id(used: set[int]) -> str:
    while True:
        value = secrets.randbelow(0x7FFFFFFF) + 1
        if value not in used:
            used.add(value)
            return f"{value:08X}"


def refresh_unique_ids(
    root: etree._Element, clone: etree._Element, owner_root: etree._Element
) -> None:
    for node in root.iter():
        if node.tag.endswith("}uniqueId") and node.get("val"):
            node.set("val", "{" + str(uuid.uuid4()).upper() + "}")
    w14 = "http://schemas.microsoft.com/office/word/2010/wordml"
    attributes = (f"{{{w14}}}paraId", f"{{{w14}}}textId")
    used = {
        int(value, 16)
        for node in owner_root.iter()
        for attribute in attributes
        if (value := node.get(attribute)) and re.fullmatch(r"[0-9A-Fa-f]{8}", value)
    }
    for paragraph in clone.iter(f"{{{W}}}p"):
        for attribute in attributes:
            if paragraph.get(attribute):
                paragraph.set(attribute, _word_paragraph_id(used))
    for node in list(clone.iter(f"{{{W}}}bookmarkStart", f"{{{W}}}bookmarkEnd")):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
    for node in clone.iter():
        if node.tag.endswith("}creationId") and node.get("id"):
            node.set("id", "{" + str(uuid.uuid4()).upper() + "}")
