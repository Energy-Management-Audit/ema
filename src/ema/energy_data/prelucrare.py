"""Label-anchored import of the auditor's Prelucrare date workbooks."""

from __future__ import annotations

from pathlib import Path

from ema.core.office.errors import OfficeError
from ema.core.office.sheets import Book, CellRef, open_book
from ema.energy_data.carriers import Carrier, carrier_for
from ema.energy_data.factors import FACTORS_2026, FactorTable
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading
from ema.energy_data.prelucrare_factors import read_factors
from ema.energy_data.prelucrare_tables import (
    coke_series,
    physical,
    water_tables,
)
from ema.energy_data.prelucrare_tables import months_in as _months
from ema.energy_data.prelucrare_types import (
    PrelucrareData,
    cell_or_blank,
    numeric,
    sheet_named,
    year_label,
)
from ema.energy_data.source import Located, ReaderIssue, located, normal

PHYSICAL = (
    ("Consum Electric", ("[MWh]",), Carrier.electricity_grid, "MWh"),
    ("Consum Gaz", ("[MWh]",), Carrier.natural_gas, "MWh"),
    ("Consum electrica fotovoltaic", ("[MWh]",), Carrier.electricity_pv, "MWh"),
    ("energi electrica din cogenerar", ("[MWh]",), Carrier.electricity_cogen, "MWh"),
    ("Consum Coji floarea soarelui", ("[Gcal]",), Carrier.sunflower_husks, "Gcal"),
    ("Consum Energie termica terti", ("[Gcal]",), Carrier.purchased_heat, "Gcal"),
    ("Consum Carburanti", ("Motorina [t]", "Motorina"), Carrier.diesel, "t"),
    ("Consum Carburanti", ("Benzina [t]", "Benzina"), Carrier.petrol, "t"),
    ("Consum Carburanti", ("GPL [t]", "GPL"), Carrier.lpg, "t"),
    ("Consum Carburanti", ("CTL [t]",), Carrier.ctl, "t"),
    ("consum apa potabila", ("[m3]",), Carrier.water_potable, "m3"),
    ("consum apa industriala", ("[m3]",), Carrier.water_industrial, "m3"),
    ("consum apa pluviala", ("[m3]",), Carrier.water_storm, "m3"),
)


def _economics(book: Book, out: PrelucrareData) -> tuple[dict[int, Reading], dict[int, Reading]]:  # noqa: C901, PLR0912, PLR0915
    sheet = sheet_named(book, "Chelt-Cifra afaceri", out.issues)
    if sheet is None:
        out.issues.append(ReaderIssue("sheet_missing", "Chelt-Cifra afaceri"))
        return {}, {}
    columns: dict[int, int] = {}
    for row in range(1, sheet.max_row + 1):
        if any(
            normal(str(cell_or_blank(sheet, row, col).value or "")) == "anul"
            for col in range(1, sheet.max_col + 1)
        ):
            columns = {
                year: col
                for col in range(1, sheet.max_col + 1)
                if (year := year_label(cell_or_blank(sheet, row, col).value)) in out.dataset.years
            }
            break
    turnover_rows: dict[str, int] = {}
    costs_row: int | None = None
    source_labels: dict[int, str] = {}
    for row in range(1, sheet.max_row + 1):
        labels = [
            normal(value)
            for col in range(1, sheet.max_col + 1)
            if isinstance((value := cell_or_blank(sheet, row, col).value), str)
        ]
        label_col = next(
            (
                col
                for col in range(1, sheet.max_col + 1)
                if isinstance((value := cell_or_blank(sheet, row, col).value), str)
                and (
                    "cifra de afaceri" in normal(value)
                    or "veniturilor din exploatare" in normal(value)
                    or "cheltuieli de productie" in normal(value)
                    or "cheltuieli energetice totale" in normal(value)
                    or "cheltuieli cu energia" in normal(value)
                )
            ),
            None,
        )
        if label_col is not None:
            raw_label = str(cell_or_blank(sheet, row, label_col).value or "")
            source_labels[row] = raw_label
            label = normal(raw_label)
            if "cifra de afaceri" in label:
                turnover_rows["turnover"] = row
            elif "veniturilor din exploatare" in label:
                turnover_rows.setdefault("revenue", row)
            elif "cheltuieli de productie" in label:
                turnover_rows.setdefault("production_costs", row)
            elif "cheltuieli energetice totale" in label or "cheltuieli cu energia" in label:
                costs_row = row
        if any("intensitate energetica tep 1000 lei" in label for label in labels):
            for year, col in columns.items():
                cell = cell_or_blank(sheet, row, col)
                value = numeric(cell.value)
                if value is not None:
                    out.filed[f"intensity.{year}"] = located(cell, value, "tep/1000 lei")
        if (
            "ponderea" in labels
            and row > 2
            and any(
                "valoarea totala a productiei"
                in normal(str(cell_or_blank(sheet, row - 2, col).value or ""))
                for col in range(1, sheet.max_col + 1)
            )
        ):
            for year, col in columns.items():
                cell = cell_or_blank(sheet, row, col)
                value = numeric(cell.value)
                if value is not None:
                    out.filed[f"energy_share.{year}"] = located(cell, value, "%")

    def values(row: int | None) -> dict[int, tuple[Reading, Located]]:
        result: dict[int, tuple[Reading, Located]] = {}
        if row is None:
            return result
        for year, col in columns.items():
            cell = cell_or_blank(sheet, row, col)
            value = numeric(cell.value)
            if value is not None:
                result[year] = (
                    Reading(value, "lei"),
                    located(cell, value, "lei", source_labels.get(row)),
                )
        return result

    primary = values(turnover_rows.get("turnover"))
    fallback = values(turnover_rows.get("revenue"))
    production_costs = values(turnover_rows.get("production_costs"))
    turnover: dict[int, Reading] = {}
    for year in columns:
        selected = primary.get(year) or fallback.get(year) or production_costs.get(year)
        if selected is not None:
            turnover[year], out.located[f"turnover.{year}"] = selected
    costs = values(costs_row)
    energy_costs = {year: reading for year, (reading, _) in costs.items()}
    out.located.update({f"energy_costs.{year}": located for year, (_, located) in costs.items()})
    return turnover, energy_costs


def _production(
    book: Book, out: PrelucrareData
) -> tuple[dict[str, dict[int, CarrierSeries]], dict[str, str]]:
    sheet = sheet_named(book, "Productii", out.issues)
    if sheet is not None:
        tonnes = physical(sheet, ("tone",), "tone", "production", out)
        if tonnes:
            out.deferred_production.update(tonnes)
            return {"main": tonnes}, {"main": "tone"}
        for label, unit, divisor in (
            ("kWh gaz vehiculat", "mii MWh gaz vehiculat", 1_000_000),
            ("tone/luna", "mii tone", 1000),
        ):
            series = physical(sheet, (label,), unit, "production", out)
            if series:
                scaled = {
                    year: CarrierSeries(
                        {
                            month: Reading(
                                reading.value / divisor if reading.value is not None else None, unit
                            )
                            for month, reading in values.months.items()
                        }
                    )
                    for year, values in series.items()
                }
                return {"main": scaled}, {"main": unit}
    sheet = sheet_named(book, "Productii-energie", out.issues)
    if sheet is not None:
        columns = {
            year: col
            for col in range(1, sheet.max_col + 1)
            if (year := year_label(cell_or_blank(sheet, 1, col).value)) in out.dataset.years
        }
        for row in range(1, sheet.max_row + 1):
            if any(
                normal(str(cell_or_blank(sheet, row, col).value or "")) == "productii tone an"
                for col in range(1, min(sheet.max_col, 3) + 1)
            ):
                result = {}
                for year, col in columns.items():
                    cell = cell_or_blank(sheet, row, col)
                    value = numeric(cell.value)
                    if value is not None:
                        result[year] = CarrierSeries(annual=Reading(value, "tone"))
                        out.located[f"production.main.{year}"] = located(cell, value, "tone")
                return {"main": result}, {"main": "tone"}
    out.issues.append(ReaderIssue("production_missing", "Productii"))
    return {}, {}


def _filed_tep(book: Book, out: PrelucrareData) -> None:  # noqa: C901
    sheet = sheet_named(book, "TEP", out.issues)
    if sheet is None:
        out.issues.append(ReaderIssue("sheet_missing", "TEP"))
        return
    current_year: int | None = None
    columns: dict[int, int] = {}
    for row in range(1, sheet.max_row + 1):
        if (
            year := year_label(cell_or_blank(sheet, row, 3).value)
        ) in out.dataset.years and not _months(sheet, row):
            current_year, columns = year, {}
            continue
        months = _months(sheet, row)
        if len(months) == 12 and current_year is not None:
            columns = months
            continue
        if current_year is None or not columns:
            continue
        label = normal(str(cell_or_blank(sheet, row, 3).value or ""))
        carrier = carrier_for(label)
        if carrier is None and label != "total tep":
            continue
        name = carrier.value if carrier else "total"
        for month, col in columns.items():
            cell = cell_or_blank(sheet, row, col)
            value = numeric(cell.value)
            if value is not None:
                out.filed[f"tep.{name}.{current_year}.{month:02d}"] = located(cell, value, "tep")
        for col in range(
            max(columns.values()) + 1, min(sheet.max_col, max(columns.values()) + 2) + 1
        ):
            try:
                cell = sheet.value(row, col)
            except OfficeError as exc:
                out.issues.append(ReaderIssue(exc.code, str(exc), CellRef(sheet.name, row, col)))
                continue
            value = numeric(cell.value)
            if value is not None:
                out.filed[f"tep.{name}.{current_year}"] = located(cell, value, "tep")


def _filed_specific(book: Book, out: PrelucrareData) -> None:  # noqa: C901
    sheet = sheet_named(book, "Consumuri specifice", out.issues)
    if sheet is None:
        out.issues.append(ReaderIssue("sheet_missing", "Consumuri specifice"))
        return
    for row in range(1, sheet.max_row + 1):
        labels: dict[int, str] = {}
        for col in range(1, sheet.max_col + 1):
            label = normal(str(cell_or_blank(sheet, row, col).value or ""))
            if "consum specific anual de energie tep" in label:
                labels[col] = "total"
            elif "consum specific anual de" in label:
                suffix = label.split("consum specific anual de", 1)[1].split(" tep", 1)[0]
                carrier = carrier_for(suffix)
                if carrier is not None:
                    labels[col] = carrier.value
        if not labels:
            continue
        for later in range(row + 1, min(row + 4, sheet.max_row + 1)):
            year = year_label(cell_or_blank(sheet, later, 2).value)
            if year not in out.dataset.years:
                continue
            for col, name in labels.items():
                cell = cell_or_blank(sheet, later, col)
                value = numeric(cell.value)
                if value is not None:
                    out.filed[f"specific.{name}.{year}"] = located(cell, value)
        break


def _filed_production_partial(book: Book, out: PrelucrareData) -> None:
    """Keep the gas plus grid figure without treating it as the energy total."""
    sheet = sheet_named(book, "Productii", out.issues)
    if sheet is None:
        return
    for row in range(1, sheet.max_row + 1):
        columns = [
            col
            for col in range(1, sheet.max_col + 1)
            if normal(str(cell_or_blank(sheet, row, col).value or "")) == "consum specific total en"
        ]
        if len(columns) != 1:
            continue
        for later in range(row + 1, sheet.max_row + 1):
            year = year_label(cell_or_blank(sheet, later, 3).value)
            if year is None:
                break
            cell = cell_or_blank(sheet, later, columns[0])
            value = numeric(cell.value)
            if value is not None:
                out.filed[f"specific.gas_grid_partial.{year}"] = located(cell, value, "tep/tone")
        break


def import_prelucrare(path: Path) -> PrelucrareData:  # noqa: C901, PLR0912
    book = open_book(path)
    try:
        empty = EnergyDataset((), {})
        out = PrelucrareData(empty, FactorTable("empty", 1, (), ()))
        carriers: dict[Carrier, dict[int, CarrierSeries]] = {}
        for sheet_name, label, carrier, unit in PHYSICAL:
            sheet = sheet_named(book, sheet_name, out.issues)
            if sheet is None:
                continue
            series = physical(sheet, label, unit, carrier.value, out)
            if series:
                carriers[carrier] = series
                if carrier == Carrier.electricity_cogen:
                    out.deferred_series.update((carrier, year) for year in series)
        coke = sheet_named(book, "Consum Cocs", out.issues)
        if coke is not None and (series := coke_series(coke, out)):
            carriers[Carrier.coke] = series
            out.deferred_series.update((Carrier.coke, year) for year in series)
        carriers.update(water_tables(book, out))
        for carrier, by_year in tuple(carriers.items()):
            values = [
                reading.value
                for series in by_year.values()
                for reading in (*series.months.values(), series.annual)
                if reading is not None
            ]
            if any(value == 0 for value in values) and not any(
                value not in {None, 0} for value in values
            ):
                carriers.pop(carrier)
                out.issues.append(ReaderIssue("carrier_all_zero", carrier.value))
                for field in tuple(out.located):
                    if field.startswith(f"carrier.{carrier.value}."):
                        out.located.pop(field)
        years = tuple(sorted({year for series in carriers.values() for year in series}))
        out.dataset = EnergyDataset(years, carriers)
        production, units = _production(book, out)
        turnover, energy_costs = _economics(book, out)
        out.dataset = EnergyDataset(years, carriers, production, units, turnover, energy_costs)
        out.factors = read_factors(book, years, out, path.name)
        for carrier, by_year in carriers.items():
            if carrier in {Carrier.water_potable, Carrier.water_industrial, Carrier.water_storm}:
                continue
            for year, series in by_year.items():
                unit = (
                    series.annual.unit
                    if series.annual
                    else next((reading.unit for reading in series.months.values()), "")
                )
                # PV alone has a configured fallback factor when its source row is absent.
                if (
                    unit
                    and out.factors.tep_factor(carrier, unit, year) is None
                    and (
                        carrier != Carrier.electricity_pv
                        or FACTORS_2026.tep_factor(carrier, unit, year) is None
                    )
                ):
                    out.issues.append(
                        ReaderIssue("factor_missing", f"{carrier.value}.{unit}.{year}")
                    )
        _filed_tep(book, out)
        _filed_specific(book, out)
        _filed_production_partial(book, out)
        return out
    finally:
        book.close()
