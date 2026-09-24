"""Monthly Anexa 2–3 blocks with exact carrier and month matching."""

from __future__ import annotations

from ema.core.office.sheets import Book, CellRef, Sheet
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.carriers import Carrier, carrier_for
from ema.energy_data.source import Located, ReaderIssue, cell_at, normal, number, row_with

_MONTH_NAMES = {
    name: index
    for index, names in enumerate(
        (
            ("ian", "ianuarie"),
            ("feb", "februarie"),
            ("mar", "martie"),
            ("apr", "aprilie"),
            ("mai",),
            ("iun", "iunie"),
            ("iul", "iulie"),
            ("aug", "august"),
            ("sep", "septembrie"),
            ("oct", "octombrie"),
            ("noi", "noiembrie"),
            ("dec", "decembrie"),
        ),
        start=1,
    )
    for name in names
}
_KNOWN_UNITS = {"mwh", "gcal", "tone", "m3 an", "mc", "mii mc"}


def read_monthly(book: Book, result: AnexaData) -> None:
    sheet = book.sheet("Date lunare")
    _read_total(sheet, result)
    ambiguous: set[str] = set()
    for row in range(1, sheet.max_row + 1):
        labels = [(col, cell_at(sheet, row, col, result.issues).value) for col in range(1, 4)]
        anchor = next(
            (col for col, value in labels if isinstance(value, str) and normal(value) == "luna"),
            None,
        )
        if anchor is None:
            continue
        months = _month_values(sheet, row, anchor, result)
        has_unit = all(value.unit is not None for value in months.values())
        carrier = _monthly_block_carrier(sheet, row, result)
        if carrier is None:
            if months and any(value.value != 0 for value in months.values()):
                result.issues.append(
                    ReaderIssue(
                        "carrier_unknown", "monthly block", CellRef(sheet.name, row, anchor)
                    )
                )
            continue
        if months:
            if (
                carrier.value in result.monthly
                or carrier.value in result.monthly_unresolved
                or carrier.value in ambiguous
            ):
                result.monthly.pop(carrier.value, None)
                result.monthly_unresolved.pop(carrier.value, None)
                ambiguous.add(carrier.value)
                result.issues.append(
                    ReaderIssue(
                        "carrier_ambiguous", carrier.value, CellRef(sheet.name, row, anchor)
                    )
                )
            else:
                target = result.monthly if has_unit else result.monthly_unresolved
                target[carrier.value] = months


def _read_total(sheet: Sheet, result: AnexaData) -> None:
    total_row = row_with(sheet, ("CONSUM DE ENERGIE TOTAL ANUAL",), result.issues)
    if total_row is not None:
        candidates: list[Located] = []
        for col in range(1, min(sheet.max_col, 20) + 1):
            unit = cell_at(sheet, total_row, col, result.issues).value
            if isinstance(unit, str) and normal(unit) == "tep an":
                value_col = col + 3
                if value_col <= sheet.max_col:
                    value = number(
                        cell_at(sheet, total_row + 1, value_col, result.issues),
                        result.issues,
                        unit="tep/an",
                    )
                    if value is not None:
                        candidates.append(value)
        if len(candidates) == 1:
            result.monthly_total_tep = candidates[0]
        elif len(candidates) > 1:
            result.issues.append(
                ReaderIssue(
                    "monthly_total_ambiguous",
                    "Date lunare total",
                    CellRef(sheet.name, total_row, 1),
                )
            )


def _monthly_block_carrier(sheet: Sheet, month_row: int, result: AnexaData) -> Carrier | None:
    for row in (row for row in (month_row - 1, month_row - 2) if row >= 1):
        for col in range(1, min(sheet.max_col, 3) + 1):
            label = cell_at(sheet, row, col, result.issues).value
            if isinstance(label, str) and (carrier := _monthly_carrier(label)) is not None:
                return carrier
    return None


def _month_values(sheet: Sheet, row: int, anchor: int, result: AnexaData) -> dict[int, Located]:
    months: dict[int, Located] = {}
    headings: set[int] = set()
    ambiguous: set[int] = set()
    unit_cell = cell_at(sheet, row + 1, anchor, result.issues).value
    unit = unit_cell.strip(" []") if isinstance(unit_cell, str) else None
    if not unit or normal(unit) not in _KNOWN_UNITS:
        result.issues.append(
            ReaderIssue(
                "unit_missing" if not unit else "unit_unknown",
                unit if unit else "monthly",
                CellRef(sheet.name, row + 1, anchor),
            )
        )
        unit = None
    for col in range(anchor + 1, min(sheet.max_col, anchor + 15) + 1):
        month = cell_at(sheet, row, col, result.issues).value
        if not isinstance(month, str) or (index := _MONTH_NAMES.get(normal(month))) is None:
            continue
        headings.add(index)
        value = number(cell_at(sheet, row + 1, col, result.issues), result.issues, unit=unit)
        if value is not None:
            if index in months or index in ambiguous:
                result.issues.append(ReaderIssue("month_ambiguous", str(index), value.ref))
                months.pop(index, None)
                ambiguous.add(index)
            else:
                months[index] = value
        else:
            result.issues.append(
                ReaderIssue("value_missing", "monthly", CellRef(sheet.name, row + 1, col))
            )
    if len(headings) != 12:
        result.issues.append(
            ReaderIssue(
                "month_header_incomplete", str(sorted(headings)), CellRef(sheet.name, row, anchor)
            )
        )
    return months


def _monthly_carrier(label: str) -> Carrier | None:
    direct = carrier_for(label)
    if direct is not None:
        return direct
    key = normal(label)
    return {
        "energie electrica consumul total anual": Carrier.electricity_grid,
        "energie termica consumul total anual": Carrier.purchased_heat,
        "energie termica consumul total annual din surse externe": Carrier.purchased_heat,
        "energie electrica din surse recuperabile si sau regenerabile consumuri totale anuale": (
            Carrier.electricity_pv
        ),
        "alti combustibili gpl": Carrier.lpg,
        "carbune cocs": Carrier.coke,
        "apa din reteaua publica": Carrier.water_potable,
        "apa potabila din retea": Carrier.water_potable,
        "apa industriala din surse proprii": Carrier.water_industrial,
        "apa industriala din surse proprii sau din retea": Carrier.water_industrial,
    }.get(key)
