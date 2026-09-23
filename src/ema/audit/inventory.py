"""Structural inventory of document units S10b can clone as a whole."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from docx import Document
from docx.oxml.ns import qn

from ema.audit.headings import Heading, MappedHeading, map_headings, normalize


@dataclass(frozen=True)
class BaseUnit:
    kind: str
    heading_path: tuple[str, ...]
    element_range: tuple[int, int]
    matched_headers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExcludedTable:
    heading_path: tuple[str, ...]
    element_range: tuple[int, int]
    reason: str


@dataclass(frozen=True)
class BaseInventory:
    processes: tuple[BaseUnit, ...]
    equipment_lists: tuple[BaseUnit, ...]
    equipment_specs: tuple[BaseUnit, ...]
    measured_panels: tuple[BaseUnit, ...]
    measurement_tables: tuple[BaseUnit, ...]
    carriers: tuple[BaseUnit, ...]
    water: tuple[BaseUnit, ...]
    measures: tuple[BaseUnit, ...]
    excluded_tables: tuple[ExcludedTable, ...]

    @property
    def equipment_tables(self) -> tuple[BaseUnit, ...]:
        return (*self.equipment_lists, *self.equipment_specs)


def _audit_id(path: Path) -> str:
    name = path.name.lower()
    for key in ("AUDIT-01", "AUDIT-02", "AUDIT-03", "AUDIT-04", "CLIENT-A3"):
        if key in name:
            return key
    return "pcm"


def _span(
    heading: Heading, all_headings: list[Heading], positions: list[int], end: int
) -> tuple[int, int]:
    start = positions[heading.index]
    next_heading = next(
        (
            item
            for item in all_headings
            if item.index > heading.index and item.level <= heading.level
        ),
        None,
    )
    return start, positions[next_heading.index] if next_heading else end


def _path(item: MappedHeading) -> tuple[str, ...]:
    return (*item.heading.path, item.heading.text)


def _header(element: Any) -> str:
    first = element.find(qn("w:tr"))
    return normalize(" ".join(cast(list[str], list(first.itertext())))) if first is not None else ""


def _equipment_kind(header: str) -> tuple[str | None, tuple[str, ...]]:
    labels = tuple(
        label
        for label in (
            "parametrii",
            "u.m",
            "caracteristici",
            "denumire",
            "tip",
            "buc",
            "putere",
            "locatia",
            "nominal",
            "an fabricatie",
            "consumator",
        )
        if label in header
    )
    if "parametrii" in labels and ("u.m" in labels or "caracteristici" in labels):
        return "equipment_spec", labels
    if ("denumire" in labels and ("buc" in labels or "putere" in labels)) or (
        "locatia" in labels and "putere" in labels
    ):
        return "equipment_list", labels
    return None, labels


def _owner(index: int, items: list[MappedHeading], positions: list[int]) -> MappedHeading | None:
    previous = (item for item in items if positions[item.heading.index] <= index)
    return next(reversed(list(previous)), None)


def inventory(docx: Path) -> BaseInventory:  # noqa: C901, PLR0912
    document = Document(str(docx))
    body: list[Any] = list(cast(Any, document.element).body)
    positions = [i for i, element in enumerate(body) if element.tag == qn("w:p")]
    mapping = map_headings(docx, _audit_id(docx))
    items = list(mapping.mapped)
    all_headings = [item.heading for item in items]
    processes: list[BaseUnit] = []
    panels: list[BaseUnit] = []
    carriers: list[BaseUnit] = []
    water: list[BaseUnit] = []
    measures: list[BaseUnit] = []
    lists: list[BaseUnit] = []
    specs: list[BaseUnit] = []
    measurement_tables: list[BaseUnit] = []
    excluded: list[ExcludedTable] = []
    carrier_ids = {
        "ch4.electricitate",
        "ch4.gaz",
        "ch4.carburant",
        "ch4.echiv_electric",
        "ch4.echiv_gaz",
        "ch4.echiv_carburant",
        "ch4.specific_electric",
        "ch4.specific_gaz",
        "ch4.specific_carburant",
    }
    for item in items:
        section_id, heading = item.section_id, item.heading
        path = _path(item)
        span = _span(heading, all_headings, positions, len(body))
        if section_id == "ch3.process":
            processes.append(BaseUnit("process", path, span))
        if section_id in carrier_ids:
            carriers.append(BaseUnit("carrier", path, span))
        if section_id in ("ch4.apa", "ch4.specific_apa"):
            water.append(BaseUnit("water", path, span))
        if section_id == "ch6.measure":
            measures.append(BaseUnit("measure", path, span))
        if section_id == "ch5.electric_fisa":
            starts = [
                index
                for index in range(*span)
                if body[index].find(".//" + qn("a:blip")) is not None
            ]
            for number, start in enumerate(starts):
                end = starts[number + 1] if number + 1 < len(starts) else span[1]
                panels.append(BaseUnit("measured_panel", path, (start, end)))
    for index, element in enumerate(body):
        if element.tag != qn("w:tbl"):
            continue
        owner = _owner(index, items, positions)
        if owner is None:
            continue
        path = _path(owner)
        if owner.section_id.startswith("ch3"):
            kind, labels = _equipment_kind(_header(element))
            if kind == "equipment_list":
                lists.append(BaseUnit(kind, path, (index, index + 1), labels))
            elif kind == "equipment_spec":
                specs.append(BaseUnit(kind, path, (index, index + 1), labels))
            else:
                excluded.append(
                    ExcludedTable(
                        path, (index, index + 1), "header is not an equipment list or specification"
                    )
                )
        elif owner.section_id.startswith("ch5"):
            measurement_tables.append(BaseUnit("measurement_table", path, (index, index + 1)))
    return BaseInventory(
        tuple(processes),
        tuple(lists),
        tuple(specs),
        tuple(panels),
        tuple(measurement_tables),
        tuple(carriers),
        tuple(water),
        tuple(measures),
        tuple(excluded),
    )
