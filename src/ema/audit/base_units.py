"""Select whole audit units before the document is de-identified."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from docx import Document
from docx.oxml.ns import qn

from ema.audit.base_prototypes import import_formatting
from ema.audit.headings import MappedHeading, map_headings
from ema.audit.inventory import BaseUnit, inventory


@dataclass(frozen=True)
class UnitPlan:
    client_name: str
    processes: int
    carriers: frozenset[str]
    measured_panels: int
    thermal_measurements: bool
    equipment_tables: int
    measures: int

    def __post_init__(self) -> None:
        if not self.client_name.strip():
            raise ValueError("client_name is required")
        if min(self.processes, self.measured_panels, self.equipment_tables, self.measures) < 0:
            raise ValueError("unit counts must be nonnegative")
        unknown = self.carriers - {"electricity", "gas", "fuel", "water"}
        if unknown:
            raise ValueError(f"unknown carrier families: {sorted(unknown)}")


def _body(document: Any) -> list[Any]:
    return list(document.element.body)


def _remap_unique_ids(document: Any, elements: list[Any]) -> None:  # noqa: C901
    root = document.element
    for tag, attribute in (("w:bookmarkStart", "w:id"), ("wp:docPr", "id")):
        key = qn(attribute) if ":" in attribute else attribute
        used = {int(value) for node in root.iter(qn(tag)) if (value := node.get(key, "")).isdigit()}
        next_id = max(used, default=0) + 1
        replacements: dict[str, str] = {}
        for element in elements:
            for node in element.iter(qn(tag)):
                old = node.get(key)
                if old is None:
                    continue
                replacements[old] = str(next_id)
                node.set(key, str(next_id))
                next_id += 1
        if tag == "w:bookmarkStart":
            for element in elements:
                for node in element.iter(qn("w:bookmarkEnd")):
                    old = node.get(key)
                    if old in replacements:
                        node.set(key, replacements[old])
    for attribute in ("paraId", "textId"):
        key = qn(f"w14:{attribute}")
        used = {node.get(key) for node in root.iter() if node.get(key)}
        next_id = max((int(value, 16) for value in used if value is not None), default=0) + 1
        for element in elements:
            for node in element.iter():
                if node.get(key) is not None:
                    node.set(key, f"{next_id:08X}")
                    next_id += 1


def _replace_range(document: Any, start: int, end: int, copies: list[list[Any]]) -> None:
    body = document.element.body
    old = _body(document)
    before = old[start]
    for group in copies:
        cloned_group = [deepcopy(element) for element in group]
        _remap_unique_ids(document, cloned_group)
        for cloned in cloned_group:
            before.addprevious(cloned)
    for element in old[start:end]:
        body.remove(element)


def _resize(document: Any, units: tuple[BaseUnit, ...], count: int) -> None:
    if not units:
        if count:
            raise ValueError("requested unit has no prototype")
        return
    source = _body(document)
    prototype = source[slice(*units[0].element_range)]
    for unit in reversed(units):
        start, end = unit.element_range
        index = units.index(unit)
        copies = [source[start:end]] if index < count else []
        if index == 0 and count > len(units):
            copies.extend([prototype] * (count - len(units)))
        _replace_range(document, start, end, copies)


def _heading_spans(path: Path, audit: str, document: Any) -> list[tuple[MappedHeading, int, int]]:
    body = _body(document)
    positions = [i for i, element in enumerate(body) if element.tag == qn("w:p")]
    mapped = list(map_headings(path, audit).mapped)
    result: list[tuple[MappedHeading, int, int]] = []
    for item in mapped:
        next_item = next(
            (
                other
                for other in mapped
                if other.heading.index > item.heading.index
                and other.heading.level <= item.heading.level
            ),
            None,
        )
        end = positions[next_item.heading.index] if next_item else len(body) - 1
        result.append((item, positions[item.heading.index], end))
    return result


def _insert_measurements(document: Any, prototype: Path, needed: bool) -> None:
    if not needed:
        return
    source = Document(str(prototype))
    audit = "AUDIT-04" if "AUDIT-04" in prototype.name.casefold() else "AUDIT-03"
    span = next(
        (start, end)
        for item, start, end in _heading_spans(prototype, audit, source)
        if item.section_id == "ch5"
    )
    chapter_six = next(
        start
        for item, start, _ in _heading_spans(prototype, audit, source)
        if item.section_id == "ch6"
    )
    assert span[1] == chapter_six
    # AUDIT-01's catalogue ch6 is printed as chapter 5; insert before that heading.
    destination = next(
        start for item, start, _ in heading_spans_document(document) if item.section_id == "ch6"
    )
    before = _body(document)[destination]
    cloned = [deepcopy(element) for element in _body(source)[span[0] : span[1]]]
    _remap_unique_ids(document, cloned)
    import_formatting(document, source, cloned)
    for element in cloned:
        before.addprevious(element)


def heading_spans_document(document: Any) -> list[tuple[MappedHeading, int, int]]:
    # A transient copy allows the existing mapper to supply catalogue identities.
    with NamedTemporaryFile(suffix="-AUDIT-01.docx") as temporary:
        document.save(temporary.name)
        return _heading_spans(Path(temporary.name), "AUDIT-01", document)


def _remove_carriers(document: Any, source_path: Path, present: frozenset[str]) -> None:
    family = {
        "ch3.electricitate": "electricity",
        "ch3.gaz": "gas",
        "ch3.carburant": "fuel",
        "ch3.apa": "water",
        "ch4.electricitate": "electricity",
        "ch4.echiv_electric": "electricity",
        "ch4.specific_electric": "electricity",
        "ch4.gaz": "gas",
        "ch4.echiv_gaz": "gas",
        "ch4.specific_gaz": "gas",
        "ch4.carburant": "fuel",
        "ch4.echiv_carburant": "fuel",
        "ch4.specific_carburant": "fuel",
        "ch4.apa": "water",
        "ch4.specific_apa": "water",
    }
    spans = _heading_spans(source_path, "AUDIT-01", document)
    for item, start, end in reversed(spans):
        group = family.get(item.section_id)
        if group and group not in present:
            _replace_range(document, start, end, [])


def select_units(document: Any, base: Path, prototype: Path, plan: UnitPlan) -> None:
    _remove_carriers(document, base, plan.carriers)
    # Each operation changes body coordinates, so refresh the inventory.
    with _Saved(document) as current:
        _resize(document, inventory(current).measures, plan.measures)
    with _Saved(document) as current:
        _resize(document, inventory(current).equipment_tables, plan.equipment_tables)
    with _Saved(document) as current:
        _resize(document, inventory(current).processes, plan.processes)
    _insert_measurements(
        document, prototype, bool(plan.measured_panels or plan.thermal_measurements)
    )
    if plan.measured_panels or plan.thermal_measurements:
        with _Saved(document) as current:
            _resize(document, inventory(current).measured_panels, plan.measured_panels)
        if not plan.thermal_measurements:
            for item, start, end in reversed(heading_spans_document(document)):
                if item.section_id == "ch5.termic":
                    _replace_range(document, start, end, [])


class _Saved:
    def __init__(self, document: Any) -> None:
        self.document = document
        self.path: Path | None = None

    def __enter__(self) -> Path:
        temporary = NamedTemporaryFile(suffix="-AUDIT-01.docx", delete=False)
        temporary.close()
        self.path = Path(temporary.name)
        self.document.save(str(self.path))
        return self.path

    def __exit__(self, *_: object) -> None:
        if self.path is not None:
            self.path.unlink(missing_ok=True)
