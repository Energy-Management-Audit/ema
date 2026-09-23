"""Independent workbook-cell relations for reviewed missing calculations."""

from __future__ import annotations

import math

from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset

from .s3_book import Workbook, month_columns, norm, number, year
from .s3_expected import CellKey
from .s3_workbooks import _impact


def tep_rows(book: Workbook, item_year: int) -> dict[tuple[str, int | None], float]:
    """Read filed TEP rows, including the recovered-heat row outside the S3 model."""
    result: dict[tuple[str, int | None], float] = {}
    current_year = None
    columns: dict[int, int] = {}
    for row in book.sheet("TEP"):
        if len(row) > 2 and year(row[2]) is not None and not month_columns(row):
            current_year = year(row[2])
            columns = {}
            continue
        seen = month_columns(row)
        if len(seen) == 12:
            columns = seen
            continue
        if current_year != item_year or not columns or len(row) < 3:
            continue
        label = norm(row[2])
        if not label:
            continue
        for month, column in columns.items():
            value = number(row[column]) if column < len(row) else None
            if value is not None:
                key = (label, month)
                assert key not in result, f"duplicate filed TEP cell: {key}"
                result[key] = value
        last_month = max(columns.values())
        annual_values = [number(v) for v in row[last_month + 1 : last_month + 3]]
        annual = next((v for v in reversed(annual_values) if v is not None), None)
        if annual is not None:
            key = (label, None)
            assert key not in result, f"duplicate filed TEP annual cell: {key}"
            result[key] = annual
    return result


def tep_total_excluding_pv(book: Workbook, item_year: int, month: int | None) -> bool:
    rows = tep_rows(book, item_year)
    total = rows["total tep", month]
    parts = [
        value
        for (label, period), value in rows.items()
        if period == month
        and label not in {"total tep", "energie electrica surse recuperabile tep"}
    ]
    return bool(parts) and math.isclose(total, sum(parts), rel_tol=1e-9, abs_tol=1e-9)


def _production_value(book: Workbook, item_year: int) -> float:
    rows = book.sheet("Chelt-Cifra afaceri")
    header = next(row for row in rows if any(norm(v) == "anul" for v in row))
    columns = [i for i, value in enumerate(header) if year(value) == item_year]
    assert len(columns) == 1, f"ambiguous economic year: {item_year}"
    values = [
        number(row[columns[0]])
        for row in rows
        if len(row) > max(2, columns[0])
        and "valoarea totala a productiei anuale realizate si vandute" in norm(row[2])
    ]
    assert len(values) == 1 and values[0], f"missing production value: {item_year}"
    return values[0]


def _production_quantity(ds: EnergyDataset, item_year: int) -> float:
    series = ds.production["main"][item_year]
    if series.annual is not None:
        assert series.annual.value is not None
        return series.annual.value
    assert len(series.months) == 12 and all(r.value is not None for r in series.months.values())
    return sum(r.value for r in series.months.values() if r.value is not None)


def filed_relation(  # noqa: PLR0911
    name: str, key: CellKey, book: Workbook, ds: EnergyDataset, factors: FactorTable
) -> float:
    """Compute the filed side from other workbook cells, never from Ema's result."""
    item_year, month = key[3], key[4]
    rows = tep_rows(book, item_year) if name != "co2_sum" else {}
    if name == "co2_sum":
        _, filed = _impact(book, ds.years)
        parts = [
            value
            for (year_key, carrier), value in filed.items()
            if year_key == item_year and carrier
        ]
        assert parts, f"missing filed CO2 parts: {item_year}"
        return sum(parts)
    if name == "tep_sum":
        assert tep_total_excluding_pv(book, item_year, month)
        return sum(
            value
            for (label, period), value in rows.items()
            if period == month
            and label not in {"total tep", "energie electrica surse recuperabile tep"}
        )
    if name == "lpg_monthly_sum":
        parts = [rows["gpl tep", m] for m in range(1, 13)]
        return sum(parts)
    if name == "lpg_co2_from_tep":
        tep_factor = factors.tep_factor(Carrier.lpg, "t", item_year)
        co2_factor = factors.co2_factor(Carrier.lpg, "t", item_year)
        assert tep_factor is not None and tep_factor.per_unit and co2_factor is not None
        return rows["gpl tep", None] / tep_factor.per_unit * co2_factor.per_unit
    if name == "filed_production_intensity":
        return rows["total tep", None] / (_production_value(book, item_year) / 1000)
    if name == "filed_specific_total":
        return rows["total tep", None] / _production_quantity(ds, item_year)
    if name == "pv_annual_sum":
        # The annual cell is a formula over the typed monthly cells, which have no source sheet.
        label = "energie electrica surse recuperabile tep"
        if month is None:
            return sum(rows[label, m] for m in range(1, 13))
        return rows[label, None] - sum(rows[label, m] for m in range(1, 13) if m != month)
    raise AssertionError(f"unknown filed relation: {name}")
