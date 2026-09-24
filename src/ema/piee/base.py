"""One-time CLIENT-I5 base classification; only the resulting bookmarks are used at render."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.base_map import BaseElement, BaseMap, classify, inventory, save, stamp_base
from ema.core.office.package import REL_CHART, R, read_parts, relationships, target_part, xml
from ema.piee.body_spans import build_body_spans, build_unsourced_slots
from ema.piee.identity_map import build_identity_spans
from ema.piee.monthly_figures import build_figure_groups
from ema.piee.number_spans import build_number_spans, build_year_spans
from ema.piee.toc import build_toc_manifest
from ema.piee.trends import build_trend_spans

SUPPORTED_BASE_SHA = "a4898faa399bcb9d5b88ead55aa8f6f5bdb339d2a8e472820f09f2cd2b3b3313"
BODY_PARAGRAPHS = frozenset(
    {
        1,
        7,
        9,
        11,
        12,
        14,
        16,
        17,
        20,
        24,
        30,
        36,
        48,
        58,
        72,
        77,
        78,
        79,
        81,
        83,
        90,
        112,
        124,
        125,
        131,
        146,
        162,
        165,
        171,
        193,
        201,
        208,
        218,
        219,
        230,
        237,
        274,
        275,
        294,
        343,
        355,
        357,
        359,
        363,
        387,
        390,
        413,
        414,
        *range(238, 271),
        *range(344, 352),
        130,
        132,
        134,
    }
)
TABLE_HEADER_ROWS = {
    49: 1,
    51: 1,
    104: 1,
    106: 1,
    138: 1,
    140: 1,
    184: 1,
    186: 1,
    221: 1,
    223: 1,
    277: 1,
    367: 2,
    374: 2,
    382: 1,
    395: 2,
    420: 0,
}
PIE_IMAGE_REL_IDS = frozenset({"rId21", "rId22", "rId23", "rId36", "rId37", "rId38"})
REVIEWED_FIXED_NUMBER_BODY = frozenset({5, 415, 416, 417})
NUMERIC = re.compile(r"(?<!\d)(?:20\d\d|\d{3,}|\d+[,.]\d+)(?!\d)")
SECTION_RANGES = {
    "electricity_pv": (114, 164),
    "natural_gas": (165, 191),
    "fuel": (192, 234),
    "water": (236, 270),
    "specific_water": (342, 351),
}


def _text(node: etree._Element) -> str:
    return "".join(part.text or "" for part in node.iter(qn("w:t"))).strip()


def _body(parts: dict[str, bytes]) -> list[etree._Element]:
    root = xml(parts, "word/document.xml")
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("base has no body")
    return list(body)


def identity_terms(parts: dict[str, bytes]) -> tuple[str, ...]:  # noqa: C901, PLR0912
    """Extract base-client identifiers from authored identity and signature locations."""
    body = _body(parts)
    title = _text(body[0])
    match = re.search(r"\bîn cadrul\s+(.+?)\s+-\s+20\d\d", title, re.I)
    if match is None:
        raise ValueError("base title has no client identity")
    name = match.group(1).strip()
    short = re.sub(r"\s+(?:SRL|SA|S\.R\.L\.|S\.A\.)$", "", name, flags=re.I)
    terms = [name, short]
    if len(short.split()) > 1:
        terms.append(short.split()[0])
    for index in (9, 11, 12, 16, 17, 20, 30):
        value = _text(body[index - 1])
        if index == 9:
            address = value.split(":", 1)[-1].strip()
            terms.append(address)
            terms.extend(part.strip() for part in address.split(",") if len(part.strip()) >= 8)
        elif index == 11:
            terms.extend(re.findall(r"\bJ\d[\w/.-]+", value))
        elif index == 12:
            terms.extend(re.findall(r"\b\d{6,10}\b", value))
        elif index == 16:
            terms.extend(re.findall(r"(?:\+\s?\d[\d\s/-]{6,})", value))
        elif index == 17:
            terms.extend(re.findall(r"https?://[^\s;]+", value))
        elif index == 20:
            terms.extend(re.findall(r"\b\d{4}:\s+([^.,;]+)", value))
        elif index == 30:
            product = re.search(r"\bcantitatea de\s+([^,.;]+)", value, re.I)
            if product is not None:
                terms.append(product.group(1).strip())
                terms.append(product.group(1).split()[0])
    signature = body[419]
    if signature.tag == qn("w:tbl"):
        cells = list(signature.iter(qn("w:tc")))
        if len(cells) > 1:
            contact_lines = [
                _text(paragraph) for paragraph in cells[1].iter(qn("w:p")) if _text(paragraph)
            ]
            if len(contact_lines) > 1:
                terms.append(contact_lines[1])
    return tuple(
        sorted({term.strip() for term in terms if len(term.strip()) >= 5}, key=str.casefold)
    )


def _variable_selectors(  # noqa: C901, PLR0912, PLR0915
    parts: dict[str, bytes], terms: tuple[str, ...], items: tuple[BaseElement, ...]
) -> dict[str, str]:
    root = xml(parts, "word/document.xml")
    body = _body(parts)
    paths: dict[str, str] = {}
    fixed_numeric_paths = {_element_path(body[index - 1]) for index in REVIEWED_FIXED_NUMBER_BODY}

    def mark(kind: str, owner: str, node: etree._Element, slot: str) -> None:
        selector = node.getroottree().getelementpath(node)
        paths[f"{kind}:{owner}:{selector}"] = slot

    for index, node in enumerate(body, 1):
        if node.tag == qn("w:p") and index in BODY_PARAGRAPHS:
            mark("paragraph", "word/document.xml", node, f"body_{index}")
        if node.tag != qn("w:tbl") or index not in TABLE_HEADER_ROWS:
            continue
        rows = node.findall(qn("w:tr"))
        first = TABLE_HEADER_ROWS[index]
        if len(rows) <= first:
            raise ValueError(f"base table {index} has no data row")
        mark("row", "word/document.xml", rows[first], f"table_{index}_rows")
        for row_number, row in enumerate(rows[first:], first):
            for cell_number, cell in enumerate(row.findall(qn("w:tc"))):
                mark(
                    "cell", "word/document.xml", cell, f"table_{index}_r{row_number}_c{cell_number}"
                )
    for owner in parts:
        if not owner.startswith("word/") or not owner.endswith(".xml"):
            continue
        if owner.startswith(("word/charts/", "word/theme/", "word/styles")):
            continue
        document = xml(parts, owner)
        for paragraph in document.iter(qn("w:p")):
            value = _text(paragraph).casefold()
            if not value or not any(term.casefold() in value for term in terms):
                continue
            key = f"paragraph:{owner}:{paragraph.getroottree().getelementpath(paragraph)}"
            if key not in paths:
                slot = f"identity_{len(paths)}"
                paths[key] = slot
    for chart in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/chart}chart"):
        rid = chart.get(f"{{{R}}}id")
        rel = next(
            (
                item
                for item in relationships(parts, "word/document.xml")
                if item.get("Id") == rid and item.get("Type") == REL_CHART
            ),
            None,
        )
        if rel is None:
            raise ValueError("base chart relationship missing")
        part = target_part("word/document.xml", rel.get("Target", ""))
        slot = "chart_" + part.rsplit("chart", 1)[-1].removesuffix(".xml")
        mark("chart", "word/document.xml", chart, slot)
        paths[f"chart_part:{part}:/"] = slot
        paths[f"relationship:word/_rels/document.xml.rels:{rid}"] = slot
    for picture in root.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
        rid = picture.get(f"{{{R}}}embed")
        if rid in PIE_IMAGE_REL_IDS:
            slot = f"pie_{rid}"
            mark("picture", "word/document.xml", picture, slot)
            paths[f"relationship:word/_rels/document.xml.rels:{rid}"] = slot
    for owner in parts:
        if not owner.startswith("word/") or not owner.endswith(".xml"):
            continue
        if owner.startswith(("word/charts/", "word/theme/", "word/styles")):
            continue
        document = xml(parts, owner)
        for link in document.iter(qn("w:hyperlink")):
            rid = link.get(f"{{{R}}}id")
            if not rid:
                continue
            rel = next(
                (item for item in relationships(parts, owner) if item.get("Id") == rid), None
            )
            if rel is None:
                continue
            content = (_text(link) + " " + rel.get("Target", "")).casefold()
            if any(term.casefold() in content for term in terms):
                slot = f"hyperlink_{len(paths)}"
                mark("hyperlink", owner, link, slot)
                rel_owner = owner.rsplit("/", 1)
                rel_path = f"{rel_owner[0]}/_rels/{rel_owner[1]}.rels"
                paths[f"relationship:{rel_path}:{rid}"] = slot
    for owner in ("docProps/core.xml", "docProps/app.xml"):
        if owner not in parts:
            continue
        document = xml(parts, owner)
        for child in document:
            if child.text and any(term.casefold() in child.text.casefold() for term in terms):
                paths[f"property:{owner}:{child.getroottree().getelementpath(child)}"] = "body_1"
    for number in (1, 3):
        owner = f"word/footer{number}.xml"
        paragraphs = list(xml(parts, owner).iter(qn("w:p")))
        if len(paragraphs) != 4:
            raise ValueError("base first-page footer structure changed")
        mark("paragraph", owner, paragraphs[1], f"footer_address_{number}")
        mark("paragraph", owner, paragraphs[2], f"footer_contact_{number}")
    for entry in items:
        if entry.kind not in {"paragraph", "cell"} or entry.id in paths:
            continue
        node = xml(parts, entry.owner).find(entry.selector)
        if node is None:
            continue
        if entry.kind == "paragraph":
            parent_cell = next(node.iterancestors(qn("w:tc")), None)
            if parent_cell is not None:
                cell_id = (
                    f"cell:{entry.owner}:{parent_cell.getroottree().getelementpath(parent_cell)}"
                )
                if cell_id in paths:
                    paths[entry.id] = paths[cell_id]
                    continue
        if not NUMERIC.search(_text(node)):
            continue
        if (
            entry.owner == "word/document.xml"
            and node.tag == qn("w:p")
            and entry.selector in fixed_numeric_paths
        ):
            continue
        paths[entry.id] = f"number_{len(paths)}"
    for group, (first, last) in SECTION_RANGES.items():
        for bound, index in (("start", first), ("end", last)):
            node = body[index - 1]
            if node.tag != qn("w:p"):
                raise ValueError(f"section {group} {bound} is not a paragraph")
            key = f"paragraph:word/document.xml:{node.getroottree().getelementpath(node)}"
            paths.setdefault(key, f"section_{group}_{bound}")
    return paths


def _numeric_leftovers(parts: dict[str, bytes], mapping: BaseMap) -> list[str]:
    body = _body(parts)
    allowed = {
        f"paragraph:word/document.xml:{_element_path(body[index - 1])}"
        for index in REVIEWED_FIXED_NUMBER_BODY
    }
    issues: list[str] = []
    for entry in mapping.elements:
        if entry.classification != "fixed" or entry.kind not in {"paragraph", "cell"}:
            continue
        node = xml(parts, entry.owner).find(entry.selector)
        if node is not None and NUMERIC.search(_text(node)) and entry.id not in allowed:
            issues.append(entry.id)
    return issues


def _groups(parts: dict[str, bytes], mapping: BaseMap) -> dict[str, tuple[str, str]]:
    body = _body(parts)
    slots = {entry.id: entry.slot for entry in mapping.elements}
    result: dict[str, tuple[str, str]] = {}
    for name, (start, end) in SECTION_RANGES.items():
        endpoints = [
            slots[f"paragraph:word/document.xml:{_element_path(body[index - 1])}"]
            for index in (start, end)
        ]
        if any(slot is None for slot in endpoints):
            raise ValueError(f"section {name} has an unanchored boundary")
        result[name] = (str(endpoints[0]), str(endpoints[1]))
    return result


def _element_path(node: etree._Element) -> str:
    return node.getroottree().getelementpath(node)


def build_local_base(base: Path, workspace_directory: Path) -> BaseMap:
    """Build private map, denylist, stamped base and visible preview for human review."""
    if hashlib.sha256(base.read_bytes()).hexdigest() != SUPPORTED_BASE_SHA:
        raise ValueError("unsupported PIEE base version; classify the new base separately")
    parts = read_parts(base)
    terms = identity_terms(parts)
    items = inventory(base)
    variable = _variable_selectors(parts, terms, items)
    known = {entry.id for entry in items}
    if set(variable) - known:
        raise ValueError("PIEE base selector no longer matches inventory")
    mapping = classify(base, variable)
    numeric_issues = _numeric_leftovers(parts, mapping)
    if numeric_issues:
        raise ValueError(
            f"fixed numeric base content lacks reviewed allow-list: {len(numeric_issues)}"
        )
    workspace_directory.mkdir(parents=True, exist_ok=True)
    save(mapping, workspace_directory / "base-map.json")
    build_identity_spans(parts, mapping, workspace_directory / "identity-spans.json")
    build_body_spans(parts, mapping, workspace_directory / "body-spans.json")
    build_unsourced_slots(parts, mapping, workspace_directory / "unsourced-slots.json")
    build_number_spans(parts, mapping, workspace_directory / "number-spans.json")
    build_year_spans(parts, mapping, workspace_directory / "year-spans.json")
    build_trend_spans(parts, mapping, workspace_directory / "trend-spans.json")
    build_figure_groups(parts, mapping, workspace_directory / "figure-groups.json")
    build_toc_manifest(parts, mapping, workspace_directory / "toc-manifest.json")
    (workspace_directory / "base-identity.json").write_text(
        json.dumps(terms, ensure_ascii=False), encoding="utf-8"
    )
    (workspace_directory / "section-groups.json").write_text(
        json.dumps(_groups(parts, mapping)), encoding="utf-8"
    )
    stamp_base(base, mapping, workspace_directory / "piee-master.docx")
    stamp_base(base, mapping, workspace_directory / "piee-preview.docx", preview=True)
    return mapping
