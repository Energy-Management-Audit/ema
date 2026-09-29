"""S10 level-2 reference check: only the auditor's structural headings, no body text."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from docx import Document
from tests.golden.cases import case_path

from ema.audit.catalogue import CATALOGUE, AuditFact
from ema.audit.headings import headings, map_headings
from ema.audit.inventory import inventory

pytestmark = pytest.mark.golden

FILES = ("audit-01", "audit-02", "audit-03", "audit-04", "audit-05", "audit-06")
EXPECTED_MAP = {
    "audit-01": (53, 0),
    "audit-02": (48, 0),
    "audit-03": (63, 0),
    "audit-04": (48, 0),
    "audit-05": (41, 0),
    "audit-06": (40, 6),
}
EXPECTED_INVENTORY = {
    "audit-01": (2, 1, 1, 0, 0, 9, 2, 5),
    "audit-03": (6, 2, 39, 6, 2, 9, 2, 3),
    "audit-02": (0, 0, 0, 0, 0, 9, 0, 4),
}
INVENTORY_KINDS = (
    "processes",
    "equipment_lists",
    "equipment_specs",
    "measured_panels",
    "measurement_tables",
    "carriers",
    "water",
    "measures",
)
PV_FROM_PIEE = {
    "ch4.electricitate_pv",
    "ch4.echiv_pv",
    "ch4.specific_pv",
}


def _references() -> dict[str, Path]:
    return {audit: case_path(audit) for audit in FILES}


def _condition(section) -> str:  # type: ignore[no-untyped-def]
    condition = section.applies_when
    if condition.op == "carrier":
        return "carrier(" + ",".join(item.value for item in condition.carriers) + ")"
    if condition.op in ("always", "material", "fact"):
        return f"{condition.op}({condition.key})" if condition.key else condition.op
    return f"{condition.op}({','.join(_condition_inner(c) for c in condition.children)})"


def _condition_inner(condition) -> str:  # type: ignore[no-untyped-def]
    return f"{condition.op}({condition.key})"


def test_pv_source_heading_in_piee() -> None:
    piee = (
        Path(os.environ["EMA_REFERENCE"])
        / "piee/finished-programs/Program de îmbunătățire a eficienței energetice MODEL_2026.docx"
    )
    assert piee.is_file()
    pv_title = next(section.title for section in CATALOGUE if section.id == "ch4.electricitate_pv")
    found = any(pv_title in paragraph.text for paragraph in Document(piee).paragraphs)
    assert found, "PIEE PV source heading missing"


def test_reference_heading_union_and_inventory() -> None:  # noqa: C901, PLR0912
    paths = _references()
    maps = {audit: map_headings(path, audit) for audit, path in paths.items()}
    print("audit | by level | mapped | NOT_SECTIONS | old_template_only | captions | unmapped")
    for audit, path in paths.items():
        mapping = maps[audit]
        levels = dict(sorted(Counter(h.level for h in headings(path)).items()))
        print(
            f"{audit} | {levels} | {len(mapping.mapped)} | {len(mapping.not_sections)} | "
            f"{len(mapping.old_template_only)} | {len(mapping.excluded_captions)} | "
            f"{len(mapping.unmapped)}"
        )
        assert not mapping.unmapped, [(heading.text, heading.path) for heading in mapping.unmapped]
        if audit != "audit-06":
            assert not mapping.old_template_only
        assert (len(mapping.mapped), len(mapping.old_template_only)) == EXPECTED_MAP[audit]
    print("id | kind | applies_when | prototype | audits")
    for section in CATALOGUE:
        present = [
            audit
            for audit in FILES
            if audit != "audit-06"
            and any(item.section_id == section.id for item in maps[audit].mapped)
        ]
        print(
            f"{section.id} | {section.kind} | {_condition(section)} | "
            f"{section.prototype.audit} | {','.join(present)}"
        )
        if section.id in PV_FROM_PIEE:
            assert not present, section.id
            assert section.prototype.audit == "piee_model_2026"
        else:
            assert present, section.id
            assert section.prototype.audit in present, section.id
    print("audit fact key | sections")
    for key in AuditFact:
        users = [section.id for section in CATALOGUE if key in section.facts]
        print(f"{key.value} | {','.join(users)}")
        assert users
    template_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for audit, mapping in maps.items():
        for item in mapping.mapped:
            if item.slots:
                template_counts[(item.section_id, item.safe_text)][audit] += 1
    print("template section | masked heading | audit counts")
    for (section, masked), counts in sorted(template_counts.items()):
        print(f"{section} | {masked} | {dict(counts)}")
    for audit in ("audit-01", "audit-03", "audit-02"):
        result = inventory(paths[audit])
        mapping = maps[audit]
        safe = {item.heading.text: item.safe_text for item in mapping.mapped}
        print(f"inventory {audit}")
        assert (
            tuple(len(getattr(result, kind)) for kind in INVENTORY_KINDS)
            == (EXPECTED_INVENTORY[audit])
        )
        for kind in INVENTORY_KINDS:
            units = getattr(result, kind)
            print(f"  {kind}: {len(units)}")
            for unit in units:
                path = "/".join(safe.get(part, part) for part in unit.heading_path)
                labels = f" [{','.join(unit.matched_headers)}]" if unit.matched_headers else ""
                print(f"    {path}{labels}")
        print(f"  excluded_tables: {len(result.excluded_tables)} (non-equipment header)")
