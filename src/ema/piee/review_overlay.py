"""Carry the auditor's review decisions into the PIEE data a draft is composed from."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from typing import Any

from openpyxl.utils.cell import column_index_from_string

from ema.core.office.sheets import CellRef
from ema.core.review.models import Cell, Field
from ema.energy_data.anexa_cells import Measure
from ema.energy_data.carriers import Carrier
from ema.energy_data.model import CarrierSeries, Reading
from ema.energy_data.prelucrare_types import PrelucrareData
from ema.energy_data.source import Located
from ema.piee.dataset import PieeData

_A1 = re.compile(r"\$?([A-Z]{1,3})\$?([0-9]+)")
_GROUPS = {
    "planned": "planned_measures",
    "existing": "existing_measures",
    "audit": "audit_measures",
}
_MEASURE_ATTRIBUTES = ("description", "commissioning_year", "location")
_PAYBACK_INPUTS = ("investment_thousand_lei", "saving_thousand_lei")


def decided(field: Field) -> bool:
    return (
        field.review == "corrected"
        or (field.review == "accepted" and field.chosen is not None)
        or field.state == "manual"
    )


def _cell_ref(locator: Cell) -> CellRef | None:
    sheet, separator, a1 = locator.ref.rpartition("!")
    match = _A1.fullmatch(a1)
    if not separator or match is None:
        return None
    return CellRef(sheet or locator.sheet, int(match.group(2)), column_index_from_string(match[1]))


def _located(field: Field, value: Any, cells: Mapping[str, Cell]) -> Located:
    candidate = next((item for item in field.alternatives if item.id == field.chosen), None)
    for evidence_id in candidate.evidence if candidate is not None else field.evidence:
        cell = cells.get(evidence_id)
        ref = _cell_ref(cell) if cell is not None else None
        if ref is not None:
            return Located(value, ref, field.unit)
    return Located(value, CellRef("review", 1, 1), field.unit, label=field.key)


def _plain(value: Any) -> Any:
    return float(value) if isinstance(value, Decimal) else value


class _Overlay:
    """Mutable copies of the parts of PieeData a review decision can reach."""

    def __init__(self, data: PieeData, by_key: dict[str, Field]) -> None:
        self.data = data
        self.by_key = by_key
        self.identity = dict(data.anexa.identity)
        self.measures = {group: list(getattr(data.anexa, name)) for group, name in _GROUPS.items()}
        self.carriers = {carrier: dict(years) for carrier, years in data.dataset.carriers.items()}
        self.indicators = {key: dict(years) for key, years in data.dataset.filed_indicators.items()}
        self.filed = dict(data.prelucrare.filed) if data.prelucrare is not None else None

    def keeps(self, key: str) -> bool:
        field = self.by_key.get(key)
        return field is not None and decided(field) and field.review != "rejected"

    def drop_filed(self, keys: list[str]) -> None:
        if self.filed is not None:
            for key in keys:
                self.filed.pop(key, None)

    def annual_changed(self, carrier: Carrier, year: int) -> None:
        keys = [f"tep.{carrier.value}.{year}"]
        if not self.keeps("annual.total_tep"):
            keys.append(f"tep.total.{year}")
        if self.filed is not None:
            keys.extend(key for key in self.filed if re.fullmatch(rf"specific\..+\.{year}", key))
        self.drop_filed(keys)
        for years in self.indicators.values():
            years.pop(year, None)

    def carrier(self, parts: list[str], field: Field, value: Any) -> None:
        unit_field = parts[-1] == "unit"
        path = parts[:-1] if unit_field else parts
        if path[1] not in Carrier._value2member_map_ or not path[2].isdigit():
            return
        if len(path) == 4 and not (path[3].isdigit() and 1 <= int(path[3]) <= 12):
            return
        carrier, year = Carrier(path[1]), int(path[2])
        month = int(path[3]) if len(path) == 4 else None
        series = self.carriers.setdefault(carrier, {}).get(year, CarrierSeries())
        old = series.months.get(month) if month is not None else series.annual
        unit = old.unit if old is not None else field.unit
        if unit_field:
            if old is None:
                return
            new = Reading(old.value, str(value)) if value is not None else Reading(None, old.unit)
        elif unit is None:
            return
        else:
            new = Reading(float(value) if value is not None else None, unit)
        if new == old:
            return
        if month is None:
            self.carriers[carrier][year] = replace(series, annual=new)
            self.annual_changed(carrier, year)
        else:
            self.carriers[carrier][year] = replace(series, months={**series.months, month: new})
            self.drop_filed(
                [f"tep.{carrier.value}.{year}.{month:02d}", f"tep.total.{year}.{month:02d}"]
            )

    def measure(
        self, parts: list[str], field: Field, value: Any, cells: Mapping[str, Cell]
    ) -> None:
        group, index, column = parts[1], parts[2], parts[3]
        if group not in _GROUPS or not index.isdigit():
            return
        rows = self.measures[group]
        position = int(index) - 1
        if not 0 <= position < len(rows):
            return
        row: Measure = rows[position]
        located = _located(field, _plain(value), cells) if value is not None else None
        if column == "description":
            row = replace(row, description=located or Located("", row.description.ref))
        elif column in _MEASURE_ATTRIBUTES:
            row = replace(row, **{column: located})
        else:
            values = dict(row.values)
            old = values.pop(column, None)
            if located is not None:
                values[column] = located
            changed = (old.value if old else None) != (located.value if located else None)
            if (
                column in _PAYBACK_INPUTS
                and changed
                and not self.keeps(".".join([*parts[:3], "payback_years"]))
            ):
                values.pop("payback_years", None)
            row = replace(row, values=values)
        rows[position] = row

    def total_tep(self, field: Field, value: Any, cells: Mapping[str, Cell]) -> None:
        key = f"tep.total.{self.data.year}"
        if value is None:
            self.drop_filed([key])
            return
        if self.filed is None:
            self.filed = {}
        self.filed[key] = _located(field, _plain(value), cells)

    def build(self) -> PieeData:
        data = self.data
        anexa = replace(
            data.anexa,
            identity=self.identity,
            **{name: self.measures[group] for group, name in _GROUPS.items()},
        )
        dataset = replace(data.dataset, carriers=self.carriers, filed_indicators=self.indicators)
        prelucrare = data.prelucrare
        if self.filed is not None:
            prelucrare = (
                replace(prelucrare, filed=self.filed)
                if prelucrare is not None
                else PrelucrareData(dataset=data.dataset, factors=data.factors, filed=self.filed)
            )
        return replace(data, anexa=anexa, dataset=dataset, prelucrare=prelucrare)


def apply_review(data: PieeData, fields: list[Field], cells: Mapping[str, Cell]) -> PieeData:
    """Return a new PieeData carrying decided values; a rejected value becomes absent.

    Pending and plainly accepted fields change nothing. Values that depend on a changed reading
    are dropped so the renderers recompute them instead of printing a stale filed figure.
    """
    overlay = _Overlay(data, {field.key: field for field in fields})
    for field in fields:
        if field.review == "rejected":
            value = None
        elif decided(field):
            value = field.value
        else:
            continue
        parts = field.key.split(".")
        if parts[0] == "identity" and len(parts) == 2:
            if value is None:
                overlay.identity.pop(parts[1], None)
            else:
                overlay.identity[parts[1]] = _located(field, str(value), cells)
        elif parts[0] == "carrier" and len(parts) in (3, 4, 5):
            overlay.carrier(parts, field, value)
        elif parts[0] == "measure" and len(parts) == 4:
            overlay.measure(parts, field, value, cells)
        elif field.key == "annual.total_tep":
            overlay.total_tep(field, value, cells)
    return overlay.build()
