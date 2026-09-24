"""Read Necesar info workbooks into located, source-unit values."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from ema.core.office.sheets import Book, Sheet, open_book
from ema.energy_data.carriers import WATER_CARRIERS, Carrier
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading, field_key
from ema.energy_data.necesar_blocks import read_consumption, read_production
from ema.energy_data.necesar_model import NecesarInfo, YearValues
from ema.energy_data.necesar_tables import read_economics, read_employees, read_generic, read_other
from ema.energy_data.source import ReaderIssue, normal


def _sheet(
    book: Book, aliases: tuple[str, ...], info: NecesarInfo, *, required: bool
) -> Sheet | None:
    matches = [name for name in book.sheet_names if normal(name) in aliases]
    if not matches:
        if required:
            info.issues.append(ReaderIssue("sheet_missing", "/".join(aliases)))
        return None
    if len(matches) > 1:
        info.issues.append(ReaderIssue("sheet_ambiguous", "/".join(matches)))
        return None
    return book.sheet(matches[0])


def read_necesar_info(book: Book) -> NecesarInfo:
    info = NecesarInfo()
    sheet = _sheet(book, ("cons energetice",), info, required=True)
    if sheet is not None:
        read_consumption(sheet, info)
    sheet = _sheet(book, ("productie", "productii", "productia"), info, required=True)
    if sheet is not None:
        read_production(sheet, info)
    sheet = _sheet(book, ("cifre economice",), info, required=True)
    if sheet is not None:
        read_economics(sheet, info)
    sheet = _sheet(book, ("nr angajati",), info, required=False)
    if sheet is not None:
        read_employees(sheet, info)
    sheet = _sheet(book, ("alte consumuri",), info, required=False)
    if sheet is not None:
        read_other(sheet, info)
    for name in book.sheet_names:
        key = normal(name)
        if key in {"autovehicule", "cladiri"} or key.startswith("echipamente "):
            info.tables[key] = read_generic(book.sheet(name), info.issues)
    return info


def parse_necesar_info(path: Path) -> NecesarInfo:
    book = open_book(path)
    try:
        return read_necesar_info(book)
    finally:
        book.close()


def _series(values: YearValues, unit: str) -> CarrierSeries:
    months = {
        month: Reading(float(cast(int | float, value.value)), unit)
        for month, value in enumerate(values.months, 1)
        if value is not None
    }
    annual = (
        Reading(float(cast(int | float, values.total.value)), unit)
        if values.total is not None
        else None
    )
    return CarrierSeries(months, annual)


def _production_key(name: str) -> str:
    return normal(name).replace(" ", "_")


def to_dataset(info: NecesarInfo) -> EnergyDataset:
    carriers: dict[Carrier, dict[int, CarrierSeries]] = {}
    production: dict[str, dict[int, CarrierSeries]] = {}
    production_unit: dict[str, str] = {}
    years: set[int] = set()
    for carrier, block in info.carriers.items():
        if carrier in WATER_CARRIERS:
            continue
        carriers[carrier] = {}
        for year, values in block.years.items():
            unit = next((v.unit for v in (*values.months, values.total) if v and v.unit), None)
            if unit is None:
                continue
            field_key("carrier", carrier.value, year)
            carriers[carrier][year] = _series(values, unit)
            years.add(year)
    for item in info.production:
        key = _production_key(str(item.name.value))
        if not key:
            continue
        unit = str(item.unit.value)
        production_unit[key] = unit
        production.setdefault(key, {})
        for year, values in item.years.items():
            field_key("production", key, year)
            production[key][year] = _series(values, unit)
            years.add(year)
    turnover: dict[int, Reading] = {}
    energy_costs: dict[int, Reading] = {}
    for key, target in (("turnover_lei", turnover), ("energy_costs_lei", energy_costs)):
        for year, value in info.economics.get(key, {}).items():
            field_key("turnover" if key == "turnover_lei" else "energy_costs", None, year)
            target[year] = Reading(float(cast(int | float, value.value)), "lei")
            years.add(year)
    return EnergyDataset(
        tuple(sorted(years)), carriers, production, production_unit, turnover, energy_costs
    )
