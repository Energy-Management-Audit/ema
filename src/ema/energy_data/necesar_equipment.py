"""Boilers, forklifts, vehicles and transformers from the Necesar info equipment sheets.

The sheets are found by their column labels, never by sheet number or cell address: the next
client's file may order them differently or start a row lower.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ema.energy_data.necesar_model import GenericRow, GenericTable, NecesarInfo
from ema.energy_data.source import Located, normal

Row = dict[str, Located]


@dataclass
class NecesarEquipment:
    boilers: list[Row] = field(default_factory=list[Row])
    forklifts: list[Row] = field(default_factory=list[Row])
    vehicles: list[Row] = field(default_factory=list[Row])
    # one dict per unit, each keyed by the property label the sheet prints (Putere aparentă…)
    transformers: list[dict[str, Located]] = field(default_factory=list[dict[str, Located]])


def _column(row: GenericRow, prefix: str) -> Located | None:
    named = {normal(name): cell for name, cell in row.values.items()}
    # "Tip" is the type column, not "Tip combustibil": an exact label wins over a prefix.
    return named.get(prefix) or next(
        (cell for name, cell in named.items() if name.startswith(prefix)), None
    )


def _has(table: GenericTable, *prefixes: str) -> bool:
    names = {normal(name) for row in table.rows for name in row.values}
    return all(any(name.startswith(prefix) for name in names) for prefix in prefixes)


def _numbered(row: GenericRow, prefix: str) -> bool:
    cell = _column(row, prefix)
    return cell is not None and isinstance(cell.value, int | float)


# What the sheets fill with numbers; every other column is a name or a model, kept as text.
NUMERIC = frozenset({"count", "year", "power", "load", "hours"})


def _typed(role: str, cell: Located) -> Located:
    """A whole number as the integer the sheet shows; a model number as text."""
    value = cell.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        return cell
    if role not in NUMERIC:
        return replace(cell, value=str(int(value)) if float(value).is_integer() else str(value))
    if float(value).is_integer():
        return replace(cell, value=int(value), displayed_decimals=0)
    return cell


def _cells(row: GenericRow, roles: dict[str, str]) -> Row:
    result: Row = {}
    for role, prefix in roles.items():
        cell = _column(row, prefix)
        if cell is not None:
            result[role] = _typed(role, cell)
    return result


def _boilers(table: GenericTable) -> list[Row]:
    # The sheet prints the unit under the header: a power in anything but kW is not read.
    unit_row = next((row for row in table.rows if not _numbered(row, "nr crt")), None)
    unit = _column(unit_row, "putere instalata") if unit_row is not None else None
    kilowatts = unit is not None and normal(str(unit.value)) == "kw"
    roles = {
        "name": "denumire",
        "process": "proces de fabricatie",
        "count": "nr buc",
        "year": "an pif",
        "load": "grad mediu",
        "power": "putere instalata",
    }
    rows: list[Row] = []
    for row in table.rows:
        if not _numbered(row, "nr crt"):
            continue
        cells = _cells(row, roles)
        if "power" in cells:
            cells["power"] = replace(cells["power"], unit="kW") if kilowatts else cells["power"]
            if not kilowatts:
                del cells["power"]
        rows.append(cells)
    return rows


def _forklifts(table: GenericTable) -> list[Row]:
    roles = {
        "name": "denumire",
        "fuel": "comb",
        "capacity": "greutate",
        "year": "an fabricatie",
        "hours": "ore de functionare",
        "location": "locatie",
    }
    rows: list[Row] = []
    for row in table.rows:
        if not _numbered(row, "nr crt"):
            continue
        cells = _cells(row, roles)
        if row.continuation:
            cells["type"] = row.continuation[0]
        rows.append(cells)
    return rows


def _vehicles(table: GenericTable) -> list[Row]:
    roles = {
        "name": "denumire autovehicul",
        "maker": "producator",
        "type": "tip",
        "count": "nr buc",
        "year": "an fabricatie",
        "km": "km parcursi",
        "fuel": "tip combustibil",
        "owner": "proprietar",
    }
    return [_cells(row, roles) for row in table.rows if _column(row, "denumire autovehicul")]


def _transformers(table: GenericTable) -> list[dict[str, Located]]:
    """The property rows under the forklift list: the label in Denumire, one value per unit."""
    units: list[dict[str, Located]] = []
    for row in table.rows:
        if _numbered(row, "nr crt") or row.continuation:
            continue
        label = _column(row, "denumire")
        values = [cell for name, cell in row.values.items() if normal(name) != "denumire"]
        if label is None or not values:
            continue
        for index, cell in enumerate(values):
            if len(units) <= index:
                units.append({})
            units[index][str(label.value)] = cell
    return units


def read_equipment(info: NecesarInfo) -> NecesarEquipment:
    result = NecesarEquipment()
    for table in info.tables.values():
        if _has(table, "denumire autovehicul"):
            result.vehicles = _vehicles(table)
        elif _has(table, "proces de fabricatie", "putere instalata", "nr buc"):
            result.boilers = _boilers(table)
        elif _has(table, "greutate", "ore de functionare"):
            result.forklifts = _forklifts(table)
            result.transformers = _transformers(table)
    return result
