"""Private base-version text offsets for bookmark-addressed identity substitutions."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchor_targets import hyperlink_target
from ema.core.office.anchors import AnchorLedger, find
from ema.core.office.base_map import BaseMap
from ema.core.office.cell_text import set_paragraph_text
from ema.core.office.package import R, encoded, read_parts, write_parts, xml
from ema.core.office.run_range import TextSpan, replace_spans, visible_text


@dataclass(frozen=True)
class IdentitySpan:
    owner: str
    slot: str
    start: int
    end: int
    key: str


def _text(node: etree._Element) -> str:
    return "".join(part.text or "" for part in node.iter(qn("w:t")))


def _contact_term(signature: etree._Element) -> str | None:
    cells = list(signature.iter(qn("w:tc")))
    if len(cells) <= 1:
        return None
    lines = [_text(item).strip() for item in cells[1].iter(qn("w:p")) if _text(item).strip()]
    return lines[1] if len(lines) > 1 else None


def _field_terms(parts: dict[str, bytes]) -> dict[str, str]:  # noqa: C901
    document = xml(parts, "word/document.xml")
    body = document.find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE base has no body")
    children = list(body)
    title = _text(children[0])
    name = re.search(r"\bîn cadrul\s+(.+?)\s+-\s+20\d\d", title, re.I)
    if name is None:
        raise ValueError("PIEE base title has no client identity")
    full = name.group(1).strip()
    short = re.sub(r"\s+(?:SRL|SA|S\.R\.L\.|S\.A\.)$", "", full, flags=re.I)
    result = {full: "client_name", short: "client_name"}
    product = re.search(r"\bcantitatea de\s+([^,.;]+)", _text(children[29]), re.I)
    if product is not None:
        phrase = product.group(1).strip()
        result[phrase] = "production_name"
        result[phrase.split()[0]] = "production_name"
    contact = _contact_term(children[419])
    if contact:
        result[contact] = "contact_person"
    for index, key in (
        (9, "address"),
        (11, "registrul_comertului"),
        (12, "cui"),
        (16, "phone_fax"),
        (17, "website"),
        (20, "caen"),
    ):
        value = _text(children[index - 1])
        payload = value.split(":", 1)[-1].strip() if index != 20 else value
        if key == "cui":
            match = re.search(r"\b\d{6,10}\b", value)
            payload = match.group(0) if match else ""
        elif key == "registrul_comertului":
            match = re.search(r"\bJ\d[\w/.-]+", value)
            payload = match.group(0) if match else ""
        elif key == "website":
            match = re.search(r"https?://[^\s;]+", value)
            payload = match.group(0) if match else ""
        elif key == "caen":
            match = re.search(r"\b\d{4}:\s+[^.;]+", value)
            payload = match.group(0) if match else ""
        if payload:
            result[payload] = key
    return result


def _footer_spans(owner: str, slot: str, value: str) -> list[IdentitySpan] | None:
    if slot.startswith("footer_address_"):
        return [IdentitySpan(owner, slot, 0, len(value), "footer_address")]
    if not slot.startswith("footer_contact_"):
        return None
    spans: list[IdentitySpan] = []
    for key, pattern in (("phone", r"Phone:\s*([^;]+)"), ("fax", r"Fax:\s*(.+)$")):
        match = re.search(pattern, value, re.I)
        if match is None:
            raise ValueError("base footer contact pattern changed")
        start, end = match.span(1)
        end -= len(match.group(1)) - len(match.group(1).rstrip())
        spans.append(IdentitySpan(owner, slot, start, end, key))
    return spans


def build_identity_spans(
    parts: dict[str, bytes], mapping: BaseMap, output: Path
) -> tuple[IdentitySpan, ...]:
    """Resolve authored words only during local map creation; persist offsets, never values."""
    terms = _field_terms(parts)
    spans: list[IdentitySpan] = []
    for entry in mapping.elements:
        if entry.kind != "paragraph" or entry.slot is None:
            continue
        node = xml(parts, entry.owner).find(entry.selector)
        if node is None:
            raise ValueError("identity map selector missing from base")
        value = visible_text(node)
        footer = _footer_spans(entry.owner, entry.slot, value)
        if footer is not None:
            spans.extend(footer)
            continue
        occupied: list[tuple[int, int]] = []
        for term, key in sorted(terms.items(), key=lambda item: len(item[0]), reverse=True):
            for match in re.finditer(re.escape(term), value, re.I):
                if any(match.start() < end and match.end() > start for start, end in occupied):
                    continue
                spans.append(IdentitySpan(entry.owner, entry.slot, match.start(), match.end(), key))
                occupied.append((match.start(), match.end()))
    output.write_text(json.dumps([asdict(item) for item in spans]), encoding="utf-8")
    return tuple(spans)


def _without_bookmarks(paragraph: etree._Element) -> etree._Element:
    clone = deepcopy(paragraph)
    for node in list(clone.iter()):
        if node.tag in {qn("w:bookmarkStart"), qn("w:bookmarkEnd")}:
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
    return clone


def _site_line(paragraph: etree._Element, site: str, address: str | None, end: str) -> None:
    suffix = "" if address is None and end == "." else end
    text = f"- Sucursala {site}: {address or 'n.d.'}{suffix}"
    set_paragraph_text(paragraph, text)
    if address is None:
        start = len(text) - len(suffix) - 4
        replace_spans(paragraph, (TextSpan(start, start + 4, "n.d.", True),))


def _render_site_addresses(paragraph: etree._Element, values: dict[str, str | None]) -> None:
    second = _without_bookmarks(paragraph)
    _site_line(paragraph, values["site_1_name"] or "n.d.", values.get("site_1_address"), ";")
    _site_line(second, values["site_2_name"] or "n.d.", values.get("site_2_address"), ".")
    paragraph.addnext(second)


def _insert_production_split(root: etree._Element, values: dict[str, str | None]) -> None:
    year = values.get("analysis_year")
    if year is None:
        raise ValueError("two-site production split needs the analysis year")
    preceding = find([root], "number_629")
    heading = preceding.getnext()
    while heading is not None and not visible_text(heading).strip():
        heading = heading.getnext()
    if heading is None or visible_text(heading).strip() != "Analiza consumului de energie":
        raise ValueError("mapped production section heading changed")
    paragraph = _without_bookmarks(preceding)
    first = values.get("site_1_production_share") or "n.d."
    second = values.get("site_2_production_share") or "n.d."
    lead = (
        f"Din totalul producției pe anul {year}, "
        f"sucursala {values['site_1_name']} are un procent de "
    )
    middle = f"% iar sucursala {values['site_2_name']} "
    text = lead + first + middle + second + "%."
    set_paragraph_text(paragraph, text)
    missing: list[TextSpan] = []
    if values.get("site_1_production_share") is None:
        missing.append(TextSpan(len(lead), len(lead) + 4, "n.d.", True))
    if values.get("site_2_production_share") is None:
        start = len(lead) + len(first) + len(middle)
        missing.append(TextSpan(start, start + 4, "n.d.", True))
    if missing:
        replace_spans(paragraph, tuple(missing))
    heading.addprevious(paragraph)


def _render_paragraph(
    paragraph: etree._Element, items: list[IdentitySpan], values: dict[str, str | None]
) -> None:
    if any(item.key == "address" for item in items) and values.get("site_2_name"):
        _render_site_addresses(paragraph, values)
        return
    replace_spans(
        paragraph,
        tuple(
            TextSpan(
                item.start,
                item.end,
                values.get(item.key) or "n.d.",
                values.get(item.key) is None,
            )
            for item in items
        ),
    )


def render_identity(
    stamped: Path,
    manifest: Path,
    values: dict[str, str | None],
    output: Path,
    ledger: AnchorLedger,
    mapping: BaseMap | None = None,
) -> None:
    """Replace mapped spans inside original runs, locating paragraphs by hidden bookmark only."""
    parts = read_parts(stamped)
    roots: dict[str, etree._Element] = {}
    grouped: dict[tuple[str, str], list[IdentitySpan]] = {}
    for item in (
        IdentitySpan(**value) for value in json.loads(manifest.read_text(encoding="utf-8"))
    ):
        grouped.setdefault((item.owner, item.slot), []).append(item)
    for (owner, slot), items in grouped.items():
        root = roots.setdefault(owner, xml(parts, owner))
        paragraph = find([root], slot)
        _render_paragraph(paragraph, items, values)
        ledger.record(slot)
    if values.get("site_2_name"):
        _insert_production_split(
            roots.setdefault("word/document.xml", xml(parts, "word/document.xml")), values
        )
    if mapping is not None:
        for entry in mapping.elements:
            if entry.kind != "hyperlink" or entry.slot is None:
                continue
            target = hyperlink_target(parts, entry.slot)
            rel_path = target.owner.rsplit("/", 1)
            relationship_owner = f"{rel_path[0]}/_rels/{rel_path[1]}.rels"
            relation_root = roots.setdefault(relationship_owner, xml(parts, relationship_owner))
            relation = next(
                (item for item in relation_root if item.get("Id") == target.relationship_id), None
            )
            if relation is None:
                raise ValueError("mapped hyperlink relationship missing")
            url = values.get("website_target")
            if url is None:
                relation_root.remove(relation)
                paragraph = find(
                    [roots.setdefault(target.owner, xml(parts, target.owner))], entry.slot
                )
                link = next(paragraph.iter(qn("w:hyperlink")))
                if f"{{{R}}}id" in link.attrib:
                    del link.attrib[f"{{{R}}}id"]
                ledger.record(entry.slot, removed=True)
            else:
                relation.set("Target", url)
                relation.set("TargetMode", "External")
                ledger.record(entry.slot)
    parts.update({owner: encoded(root) for owner, root in roots.items()})
    write_parts(parts, output)
