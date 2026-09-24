"""Label-anchored import of the auditor's Prelucrare date workbooks."""

from __future__ import annotations

from pathlib import Path

from ema.core.office.errors import OfficeError
from ema.core.office.sheets import Book, CellRef, Sheet, open_book
from ema.energy_data.carriers import Carrier, carrier_for
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading
from ema.energy_data.prelucrare_factors import read_factors
from ema.energy_data.prelucrare_types import (
    PrelucrareData,
    cell_or_blank,
    numeric,
    sheet_named,
    year_label,
)
from ema.energy_data.source import Located, ReaderIssue, normal

MONTHS = (
    "ianuarie",
    "februarie",
    "martie",
    "aprilie",
    "mai",
    "iunie",
    "iulie",
    "august",
    "septembrie",
    "octombrie",
    "noiembrie",
    "decembrie",
)
PHYSICAL = (
    ("Consum Electric", "[MWh]", Carrier.electricity_grid, "MWh"),
    ("Consum Gaz", "[MWh]", Carrier.natural_gas, "MWh"),
    ("Consum electrica fotovoltaic", "[MWh]", Carrier.electricity_pv, "MWh"),
    ("Consum Coji floarea soarelui", "[Gcal]", Carrier.sunflower_husks, "Gcal"),
    ("Consum Energie termica terti", "[Gcal]", Carrier.purchased_heat, "Gcal"),
    ("Consum Carburanti", "Motorina [t]", Carrier.diesel, "t"),
    ("Consum Carburanti", "Benzina [t]", Carrier.petrol, "t"),
    ("Consum Carburanti", "GPL [t]", Carrier.lpg, "t"),
    ("Consum Carburanti", "CTL [t]", Carrier.ctl, "t"),
    ("consum apa potabila", "[m3]", Carrier.water_potable, "m3"),
    ("consum apa industriala", "[m3]", Carrier.water_industrial, "m3"),
)


def _months(sheet: Sheet, row: int) -> dict[int, int]:
    result: dict[int, int] = {}
    for col in range(1, sheet.max_col + 1):
        label = normal(str(cell_or_blank(sheet, row, col).value or ""))
        if label in MONTHS:
            result[MONTHS.index(label) + 1] = col
    return result


def _blocks(sheet: Sheet) -> list[tuple[int, int, dict[int, int]]]:
    blocks: list[tuple[int, int, dict[int, int]]] = []
    for row in range(1, sheet.max_row + 1):
        years = [
            year_label(cell_or_blank(sheet, row, col).value)
            for col in range(1, min(sheet.max_col, 3) + 1)
        ]
        months = _months(sheet, row)
        if len(months) == 12:
            year = next((item for item in years if item is not None), None)
            if year is not None:
                blocks.append((year, row, months))
    return blocks


def _physical(
    sheet: Sheet, label: str, unit: str, key: str, out: PrelucrareData
) -> dict[int, CarrierSeries]:
    blocks = _blocks(sheet)
    found: dict[int, CarrierSeries] = {}
    for index, (year, start, months) in enumerate(blocks):
        end = blocks[index + 1][1] if index + 1 < len(blocks) else sheet.max_row + 1
        matches = [
            row
            for row in range(start + 1, end)
            if any(
                normal(str(cell_or_blank(sheet, row, col).value or "")) == normal(label)
                for col in range(1, min(sheet.max_col, 3) + 1)
            )
        ]
        if len(matches) > 1:
            out.issues.append(
                ReaderIssue("label_ambiguous", f"{key}.{year}", CellRef(sheet.name, matches[0], 1))
            )
            continue
        if not matches:
            continue
        row = matches[0]
        readings: dict[int, Reading] = {}
        for month, col in months.items():
            try:
                cell = sheet.value(row, col)
            except OfficeError as exc:
                out.issues.append(ReaderIssue(exc.code, str(exc), CellRef(sheet.name, row, col)))
                continue
            value = numeric(cell.value)
            readings[month] = Reading(value, unit)
            if value is not None:
                out.located[f"carrier.{key}.{year}.{month:02d}"] = Located(value, cell.ref, unit)
        has_month = any(reading.value is not None for reading in readings.values())
        total = cell_or_blank(sheet, row, max(months.values()) + 1)
        annual_value = numeric(total.value)
        if has_month or annual_value is not None:
            annual = Reading(annual_value, unit) if annual_value is not None else None
            found[year] = CarrierSeries(readings if has_month else {}, annual)
            if annual_value is not None:
                out.located[f"carrier.{key}.{year}"] = Located(annual_value, total.ref, unit)
    return found


def _water_table(
    book: Book, out: PrelucrareData
) -> tuple[Carrier, dict[int, CarrierSeries]] | None:
    sheet = sheet_named(book, "Consum apa", out.issues)
    if sheet is None:
        return None
    label = str(cell_or_blank(sheet, 2, 2).value or "")
    carrier = carrier_for(label)
    if carrier is None:
        out.issues.append(ReaderIssue("carrier_unknown", label, CellRef(sheet.name, 2, 2)))
        return None
    for row in range(1, sheet.max_row + 1):
        months = _months(sheet, row)
        if len(months) != 12:
            continue
        result: dict[int, CarrierSeries] = {}
        for later in range(row + 1, sheet.max_row + 1):
            year = year_label(cell_or_blank(sheet, later, 2).value)
            if year is None:
                continue
            readings: dict[int, Reading] = {}
            for month, col in months.items():
                cell = cell_or_blank(sheet, later, col)
                value = numeric(cell.value)
                readings[month] = Reading(value, "m3")
                if value is not None:
                    out.located[f"carrier.{carrier.value}.{year}.{month:02d}"] = Located(
                        value, cell.ref, "m3"
                    )
            if any(reading.value is not None for reading in readings.values()):
                result[year] = CarrierSeries(readings)
        return carrier, result
    out.issues.append(ReaderIssue("month_header_missing", sheet.name))
    return None


def _economics(book: Book, out: PrelucrareData) -> tuple[dict[int, Reading], dict[int, Reading]]:  # noqa: C901, PLR0912
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
                    or "cheltuieli energetice totale" in normal(value)
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
            elif "cheltuieli energetice totale" in label:
                costs_row = row
        if any("intensitate energetica tep 1000 lei" in label for label in labels):
            for year, col in columns.items():
                cell = cell_or_blank(sheet, row, col)
                value = numeric(cell.value)
                if value is not None:
                    out.filed[f"intensity.{year}"] = Located(value, cell.ref, "tep/1000 lei")

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
                    Located(value, cell.ref, "lei", source_labels.get(row)),
                )
        return result

    primary = values(turnover_rows.get("turnover"))
    fallback = values(turnover_rows.get("revenue"))
    turnover: dict[int, Reading] = {}
    for year in columns:
        selected = primary.get(year) or fallback.get(year)
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
        for label, unit, divisor in (
            ("kWh gaz vehiculat", "mii MWh gaz vehiculat", 1_000_000),
            ("tone/luna", "mii tone", 1000),
        ):
            series = _physical(sheet, label, unit, "production", out)
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
                        out.located[f"production.main.{year}"] = Located(value, cell.ref, "tone")
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
                out.filed[f"tep.{name}.{current_year}.{month:02d}"] = Located(
                    value, cell.ref, "tep"
                )
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
                out.filed[f"tep.{name}.{current_year}"] = Located(value, cell.ref, "tep")


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
                    out.filed[f"specific.{name}.{year}"] = Located(value, cell.ref)
        break


def import_prelucrare(path: Path) -> PrelucrareData:
    book = open_book(path)
    try:
        empty = EnergyDataset((), {})
        out = PrelucrareData(empty, FactorTable("empty", 1, (), ()))
        carriers: dict[Carrier, dict[int, CarrierSeries]] = {}
        for sheet_name, label, carrier, unit in PHYSICAL:
            sheet = sheet_named(book, sheet_name, out.issues)
            if sheet is None:
                continue
            series = _physical(sheet, label, unit, carrier.value, out)
            if series:
                carriers[carrier] = series
        water = _water_table(book, out)
        if water is not None and water[1]:
            carriers[water[0]] = water[1]
        years = tuple(sorted({year for series in carriers.values() for year in series}))
        out.dataset = EnergyDataset(years, carriers)
        production, units = _production(book, out)
        turnover, energy_costs = _economics(book, out)
        out.dataset = EnergyDataset(years, carriers, production, units, turnover, energy_costs)
        out.factors = read_factors(book, years, out, path.name)
        _filed_tep(book, out)
        _filed_specific(book, out)
        return out
    finally:
        book.close()
