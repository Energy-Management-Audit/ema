"""S10 level-2 reference check: only the auditor's structural headings, no body text."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from ema.audit.catalogue import CATALOGUE, AuditFact
from ema.audit.headings import headings, map_headings
from ema.audit.inventory import inventory

pytestmark = pytest.mark.golden

FILES = {
    "AUDIT-01": "*AUDIT-01*.docx",
    "AUDIT-02": "*AUDIT-02*.docx",
    "AUDIT-03": "*AUDIT-03*.docx",
    "AUDIT-04": "*AUDIT-04*.docx",
    "pcm": "Cap 2-3-4 V2.docx",
    "CLIENT-A3": "*CLIENT-A3*.docx",
}
EXPECTED_MAP = {
    "AUDIT-01": (53, 0),
    "AUDIT-02": (48, 0),
    "AUDIT-03": (63, 0),
    "AUDIT-04": (48, 0),
    "pcm": (41, 0),
    "CLIENT-A3": (40, 6),
}
EXPECTED_INVENTORY = {
    "AUDIT-01": (2, 1, 1, 0, 0, 9, 2, 5),
    "AUDIT-03": (6, 2, 39, 6, 2, 9, 2, 3),
    "AUDIT-02": (0, 0, 0, 0, 0, 9, 0, 4),
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


def _references() -> dict[str, Path]:
    root = Path(os.environ["EMA_REFERENCE"]) / "audit" / "finished-audits"
    assert root.is_dir(), "EMA_REFERENCE/audit/finished-audits unavailable"
    result = {}
    for audit, pattern in FILES.items():
        matches = list(root.glob(pattern))
        assert len(matches) == 1, f"{audit}: expected one reference document"
        result[audit] = matches[0]
    return result


def _condition(section) -> str:  # type: ignore[no-untyped-def]
    condition = section.applies_when
    if condition.op == "carrier":
        return "carrier(" + ",".join(item.value for item in condition.carriers) + ")"
    if condition.op in ("always", "material", "fact"):
        return f"{condition.op}({condition.key})" if condition.key else condition.op
    return f"{condition.op}({','.join(_condition_inner(c) for c in condition.children)})"


def _condition_inner(condition) -> str:  # type: ignore[no-untyped-def]
    return f"{condition.op}({condition.key})"


def test_reference_heading_union_and_inventory() -> None:  # noqa: C901
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
        if audit != "CLIENT-A3":
            assert not mapping.old_template_only
        assert (len(mapping.mapped), len(mapping.old_template_only)) == EXPECTED_MAP[audit]
    print("id | kind | applies_when | prototype | audits")
    for section in CATALOGUE:
        present = [
            audit
            for audit in FILES
            if audit != "CLIENT-A3"
            and any(item.section_id == section.id for item in maps[audit].mapped)
        ]
        print(
            f"{section.id} | {section.kind} | {_condition(section)} | "
            f"{section.prototype.audit} | {','.join(present)}"
        )
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
    for audit in ("AUDIT-01", "AUDIT-03", "AUDIT-02"):
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
