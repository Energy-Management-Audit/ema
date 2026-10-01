"""Bookmark the approved PIEE base's reusable carrier slots."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
from pathlib import Path

from docx.oxml.ns import qn

from ema.core.office.anchors import stamp
from ema.core.office.package import encoded, read_parts, write_parts, xml

PROTOTYPE_PARAGRAPHS: dict[str, dict[str, int | tuple[int, ...]]] = {
    "boundaries": {
        "pv_heading": 118,
        "gas_heading": 164,
        "fuel_heading": 199,
        "water_heading": 236,
        "equivalent_heading": 272,
        "specific_group_heading": 292,
        "specific_grid_heading": 296,
        "specific_gas_heading": 308,
        "specific_fuel_heading": 320,
        "specific_total_heading": 331,
        "specific_water_heading": 342,
        "intensity_heading": 353,
    },
    "gas": {
        "heading": 164,
        "intro": 165,
        "monthly_intro": (166, 171, 176),
        "monthly_chart": (167, 172, 177),
        "monthly_caption": (168, 173, 178),
        "monthly_observation": (170, 175, 180),
        "table_intro": 181,
        "table_caption": 182,
        "table": (184, 186),
        "annual_intro": 188,
        "annual_chart": 189,
        "annual_caption": 190,
        "annual_observation": 193,
        "annual_list_item": 195,
    },
    "water": {
        "heading": 236,
        "intro": 237,
        "monthly_intro": (238, 243, 248),
        "monthly_chart": (239, 244, 249),
        "monthly_caption": (240, 245, 250),
        "monthly_observation": (242, 247, 252),
        "table_intro": 253,
        "table_caption": 254,
        "table": (257, 259),
        "annual_intro": 261,
        "annual_chart": 262,
        "annual_caption": 263,
        "annual_observation": 266,
        "annual_list_item": 268,
    },
    "specific_gas": {
        "heading": 308,
        "intro": 310,
        "annual_chart": 311,
        "annual_caption": 312,
        "annual_observation": 314,
        "annual_list_item": 316,
    },
    "gas_annual": {
        "annual_intro": 188,
        "annual_chart": 189,
        "annual_caption": 190,
        "annual_observation": 193,
    },
}


def _build_carrier_prototypes(master: Path, manifest: Path) -> None:
    """Bookmark the approved base's reusable slots without changing its approved map."""
    parts = read_parts(master)
    root = xml(parts, "word/document.xml")
    body = root.find(qn("w:body"))
    if body is None:
        raise ValueError("PIEE base has no body")
    blocks = list(body)
    next_id = (
        max(
            (int(node.get(qn("w:id"), "0")) for node in root.iter(qn("w:bookmarkStart"))),
            default=0,
        )
        + 1
    )
    groups: dict[str, dict[str, str | list[str]]] = {}
    for group, roles in PROTOTYPE_PARAGRAPHS.items():
        selected: dict[str, str | list[str]] = {}
        for role, raw in roles.items():
            slots: list[str] = []
            for ordinal, index in enumerate(raw if isinstance(raw, tuple) else (raw,), 1):
                node = blocks[index - 1]
                paragraph = next(node.iter(qn("w:p")), None) if node.tag == qn("w:tbl") else node
                if paragraph is None or paragraph.tag != qn("w:p"):
                    raise ValueError(f"prototype {group}.{role} has no paragraph")
                slot = f"prototype_{group}_{role}_{ordinal}"
                stamp(paragraph, slot, next_id)
                next_id += 1
                slots.append(slot)
            selected[role] = slots if isinstance(raw, tuple) else slots[0]
        groups[group] = selected
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, master)
    manifest.write_text(json.dumps(groups, indent=2), encoding="utf-8")
