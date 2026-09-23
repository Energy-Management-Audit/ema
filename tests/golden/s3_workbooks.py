"""Label-anchored case-specific extraction for S3 golden comparisons."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ema.energy_data.carriers import Carrier, carrier_for
from ema.energy_data.factors import Factor, FactorTable
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading

from .s3_book import Workbook, monthly_physical, norm, number, year


def _factor_after_equals(rows: list[list[Any]], label: str) -> float | None:
    for row in rows:
        for i, cell in enumerate(row):
            if norm(label) not in norm(cell):
                continue
            equal = next((j for j in range(i + 1, len(row)) if row[j] == "="), None)
            if equal is not None and equal + 2 < len(row):
                factor = number(row[equal + 1])
                if factor is not None and norm(row[equal + 2]) == "tep":
                    return factor
    return None


def _primary_tep_factor(rows: list[list[Any]], carrier_label: str) -> float | None:
    for row in rows:
        if not any(carrier_label in norm(cell) for cell in row):
            continue
        for i, cell in enumerate(row):
            if norm(cell) == "tep" and i > 0:
                return number(row[i - 1])
    return None


_SPECS = (
    (Carrier.electricity_grid, "Consum Electric", "[MWh]", "MWh", "1 MWh"),
    (Carrier.natural_gas, "Consum Gaz", "[MWh]", "MWh", "[MWh]"),
    (Carrier.diesel, "Consum Carburanti", "Motorina [t]", "t", "1 t (motorina)"),
    (Carrier.petrol, "Consum Carburanti", "Benzina [t]", "t", "benzina"),
    (Carrier.lpg, "Consum Carburanti", "GPL [t]", "t", "tone GPL"),
    (Carrier.ctl, "Consum Carburanti", "CTL [t]", "t", "1 t (CTL"),
)


def _series_and_tep_factors(
    book: Workbook, years: tuple[int, ...]
) -> tuple[dict[Carrier, dict[int, CarrierSeries]], list[Factor]]:
    carriers: dict[Carrier, dict[int, CarrierSeries]] = {}
    factors: list[Factor] = []
    for carrier, sheet_name, row_label, unit, factor_label in _SPECS:
        rows = book.sheet(sheet_name)
        series = monthly_physical(rows, row_label, unit, years)
        if not series:
            continue
        carriers[carrier] = series
        factor = _factor_after_equals(rows, factor_label)
        if factor is None and carrier == Carrier.petrol:
            factor = _primary_tep_factor(book.sheet("Principali factori de conversie"), "benzina")
        if factor is not None:
            factors.append(Factor(carrier, unit, factor, sheet_name))
    _add_extra_series(book, years, carriers, factors)
    return carriers, factors


def _add_extra_series(
    book: Workbook,
    years: tuple[int, ...],
    carriers: dict[Carrier, dict[int, CarrierSeries]],
    factors: list[Factor],
) -> None:
    for carrier, sheet_name, physical, unit, factor_label in (
        (Carrier.electricity_pv, "Consum electrica fotovoltaic", "[MWh]", "MWh", "1 MWh"),
        (Carrier.sunflower_husks, "Consum Coji floarea soarelui", "[Gcal]", "Gcal", "1 Gcal"),
        (Carrier.purchased_heat, "Consum Energie termica terti", "[Gcal]", "Gcal", "1 Gcal"),
    ):
        if sheet_name not in book.sheets:
            continue
        rows = book.sheet(sheet_name)
        series = monthly_physical(rows, physical, unit, years)
        if series:
            carriers[carrier] = series
            factor = _factor_after_equals(rows, factor_label)
            if factor is not None:
                factors.append(Factor(carrier, unit, factor, sheet_name))
    if Carrier.electricity_pv in carriers and not any(
        factor.carrier == Carrier.electricity_pv for factor in factors
    ):
        grid = next(
            (factor for factor in factors if factor.carrier == Carrier.electricity_grid), None
        )
        if grid is not None:
            factors.append(
                Factor(
                    Carrier.electricity_pv,
                    "MWh",
                    grid.per_unit,
                    "Principali factori de conversie: energie electrica",
                )
            )


def _impact(
    book: Workbook, years: tuple[int, ...]
) -> tuple[list[Factor], dict[tuple[int, Carrier | None], float]]:
    rows = book.sheet("impact de mediu")
    factors: list[Factor] = []
    filed: dict[tuple[int, Carrier | None], float] = {}
    current_year = None
    last_fuel = None
    for row in rows:
        possible = year(row[1]) if len(row) > 1 else None
        if possible in years:
            current_year = possible
            last_fuel = None
        if current_year is None or len(row) < 9:
            continue
        label = norm(row[1])
        carrier = carrier_for(label)
        if label == "indicator global prin suprapunerea efectelor":
            value = number(row[8])
            if value is not None:
                filed[current_year, None] = value
            continue
        carrier = _impact_carrier(carrier, label, last_fuel)
        if carrier is None:
            continue
        value = number(row[8])
        if value is None:
            continue
        filed[current_year, carrier] = value
        if carrier in {Carrier.diesel, Carrier.petrol, Carrier.lpg}:
            last_fuel = carrier
        factor_cell = (
            row[5] if carrier in {Carrier.electricity_grid, Carrier.natural_gas} else row[7]
        )
        factor = number(factor_cell)
        if factor is not None:
            unit = "MWh" if carrier in {Carrier.electricity_grid, Carrier.natural_gas} else "t"
            factors.append(Factor(carrier, unit, factor, "impact de mediu", current_year))
    return factors, filed


def _impact_carrier(
    carrier: Carrier | None, label: str, last_fuel: Carrier | None
) -> Carrier | None:
    if carrier is not None:
        return carrier
    if label == "carburant":
        return Carrier.diesel
    if not label and last_fuel == Carrier.diesel:
        return Carrier.petrol
    if not label and last_fuel == Carrier.petrol:
        return Carrier.lpg
    return None


def _economic(
    book: Workbook, years: tuple[int, ...]
) -> tuple[dict[int, Reading], dict[int, float]]:
    rows = book.sheet("Chelt-Cifra afaceri")
    header = next(row for row in rows if any(norm(v) == "anul" for v in row))
    year_columns = {year(value): col for col, value in enumerate(header) if year(value) in years}
    turnover: dict[int, Reading] = {}
    intensity: dict[int, float] = {}
    for row in rows:
        label = norm(row[2]) if len(row) > 2 else ""
        if "cifra de afaceri lei" in label or "veniturilor din exploatare lei" in label:
            for item_year, col in year_columns.items():
                value = number(row[col]) if col < len(row) else None
                if value is not None and (item_year not in turnover or "veniturilor" in label):
                    turnover[item_year] = Reading(value, "lei")
        if "intensitate energetica tep 1000 lei" in label:
            for item_year, col in year_columns.items():
                value = number(row[col]) if col < len(row) else None
                if value is not None:
                    intensity[item_year] = value
    if not intensity:
        intensity = _alternate_intensity(rows, years)
    return turnover, intensity


def _alternate_intensity(rows: list[list[Any]], years: tuple[int, ...]) -> dict[int, float]:
    for i, row in enumerate(rows):
        heading_col = next((j for j, cell in enumerate(row) if norm(cell) == "intensitatea"), None)
        unit_col = next((j for j, cell in enumerate(row) if norm(cell) == "tep mii lei"), None)
        if heading_col is None or unit_col is None:
            continue
        result: dict[int, float] = {}
        for later in rows[i + 1 : i + 4]:
            item_year = year(later[heading_col]) if heading_col < len(later) else None
            value = number(later[unit_col]) if unit_col < len(later) else None
            if item_year in years and value is not None:
                result[item_year] = value
        return result
    return {}


def _production(
    book: Workbook, years: tuple[int, ...], case: str
) -> tuple[dict[str, dict[int, CarrierSeries]], dict[str, str]]:
    if case == "CLIENT-P2":
        raw = monthly_physical(book.sheet("Productii"), "tone/luna", "tone", years)
        scaled = {
            y: CarrierSeries(
                {
                    m: Reading(r.value / 1000 if r.value is not None else None, "mii tone")
                    for m, r in series.months.items()
                }
            )
            for y, series in raw.items()
        }
        return {"main": scaled}, {"main": "mii tone"}
    if case == "CLIENT-A3":
        # The labelled annual production row is the denominator of her ratio table.
        rows = book.sheet("Productii-energie")
        header = rows[0]
        cols = {year(v): i for i, v in enumerate(header) if year(v) in years}
        row = next(row for row in rows if any(norm(v) == "productii tone an" for v in row))
        return {
            "main": {
                y: CarrierSeries(annual=Reading(number(row[c]), "tone")) for y, c in cols.items()
            }
        }, {"main": "tone"}
    rows = book.sheet("Productii")
    label = "kWh gaz vehiculat" if case == "CLIENT-P1" else "valoarea productiei"
    unit = "kWh gaz vehiculat" if case == "CLIENT-P1" else "mii lei"
    series = monthly_physical(rows, label, unit, years)
    if case == "CLIENT-P1":
        series = {
            y: CarrierSeries(
                {
                    m: Reading(
                        r.value / 1_000_000 if r.value is not None else None,
                        "mii MWh gaz vehiculat",
                    )
                    for m, r in s.months.items()
                }
            )
            for y, s in series.items()
        }
        unit = "mii MWh gaz vehiculat"
    return {"main": series}, {"main": unit}


def specific_cells(
    book: Workbook, years: tuple[int, ...]
) -> dict[tuple[int, Carrier | None], float]:
    name = next(name for name in book.sheets if norm(name).startswith("consumuri specifice"))
    rows = book.sheet(name)
    heading = next(
        (
            i
            for i, row in enumerate(rows)
            if any("consum specific anual de energie tep" in norm(cell) for cell in row)
        ),
        None,
    )
    if heading is None:
        return {}
    labels = {}
    for col, cell in enumerate(rows[heading]):
        normalized = norm(cell)
        if "consum specific anual de energie tep" in normalized:
            labels[col] = None
        elif "consum specific anual de" in normalized:
            suffix = normalized.split("consum specific anual de", 1)[1].split(" tep", 1)[0]
            carrier = carrier_for(suffix)
            if carrier is not None:
                labels[col] = carrier
    result = {}
    for row in rows[heading + 1 : heading + 4]:
        item_year = year(row[1]) if len(row) > 1 else None
        if item_year not in years:
            continue
        for col, carrier in labels.items():
            value = number(row[col]) if col < len(row) else None
            if value is not None:
                result[item_year, carrier] = value
    return result


def load_case(
    path: Path, case: str, years: tuple[int, ...]
) -> tuple[
    Workbook, EnergyDataset, FactorTable, dict[tuple[int, Carrier | None], float], dict[int, float]
]:
    book = Workbook.open(path)
    carriers, tep_factors = _series_and_tep_factors(book, years)
    co2_factors, co2_filed = _impact(book, years)
    turnover, intensity = _economic(book, years)
    production, production_unit = _production(book, years, case)
    ds = EnergyDataset(years, carriers, production, production_unit, turnover)
    table = FactorTable(f"prelucrare:{case}", min(years), tuple(tep_factors), tuple(co2_factors))
    return book, ds, table, co2_filed, intensity
