"""Source-located conversion factors in Prelucrare workbooks."""

from __future__ import annotations

from ema.core.office.sheets import Book, CellRef
from ema.energy_data.carriers import Carrier, carrier_for
from ema.energy_data.factors import FACTORS_2026, Factor, FactorTable
from ema.energy_data.prelucrare_types import (
    PrelucrareData,
    cell_or_blank,
    numeric,
    sheet_named,
    year_label,
)
from ema.energy_data.source import Located, ReaderIssue, located, normal


def factors_for_output(imported: PrelucrareData, years: tuple[int, ...]) -> FactorTable:
    """Keep imported factors for its years and use documented defaults elsewhere."""
    tep: list[Factor] = []
    co2: list[Factor] = []
    for year in years:
        table = imported.factors if year in imported.dataset.years else FACTORS_2026
        for source, target, getter in (
            (table.tep, tep, table.tep_factor),
            (table.co2, co2, table.co2_factor),
        ):
            for factor in source:
                selected = getter(factor.carrier, factor.unit, year)
                if selected is not None and selected.per_unit == factor.per_unit:
                    value = Factor(
                        factor.carrier, factor.unit, factor.per_unit, factor.source, year
                    )
                    if not any(
                        existing.carrier == value.carrier
                        and existing.unit == value.unit
                        and existing.year == value.year
                        for existing in target
                    ):
                        target.append(value)
        if (
            year in imported.dataset.years
            and table.tep_factor(Carrier.electricity_pv, "MWh", year) is None
        ):
            documented = FACTORS_2026.tep_factor(Carrier.electricity_pv, "MWh", year)
            if documented is not None:
                tep.append(
                    Factor(
                        documented.carrier,
                        documented.unit,
                        documented.per_unit,
                        documented.source,
                        year,
                    )
                )
    return FactorTable("prelucrare:output", min(years), tuple(tep), tuple(co2), max(years))


def read_factors(  # noqa: C901, PLR0912, PLR0915
    book: Book, years: tuple[int, ...], out: PrelucrareData, source_file: str
) -> FactorTable:
    tep: list[Factor] = []
    for name in ("Principali factori de conversie", "Factori de conversie in MWh"):
        reference = sheet_named(book, name, out.issues)
        if reference is None:
            out.issues.append(ReaderIssue("sheet_missing", name))
            continue
        for row in range(1, reference.max_row + 1):
            labels = [
                normal(str(value))
                for col in range(1, reference.max_col + 1)
                if isinstance(value := cell_or_blank(reference, row, col).value, str)
                and normal(value) not in {"", "tep", "mwh", "kg", "t"}
            ]
            if not labels:
                continue
            for col in range(1, reference.max_col + 1):
                cell = cell_or_blank(reference, row, col)
                value = numeric(cell.value)
                if value is not None:
                    out.located[f"factor_sheet.{normal(name)}.{labels[0]}.{row}.{col}"] = located(
                        cell, value
                    )
    for sheet_name, label, carrier, unit in (
        ("Consum Electric", "1 MWh", Carrier.electricity_grid, "MWh"),
        ("Consum Gaz", "[MWh]", Carrier.natural_gas, "MWh"),
        ("Consum Carburanti", "1 t (motorina)", Carrier.diesel, "t"),
        ("Consum Carburanti", "benzina", Carrier.petrol, "t"),
        ("Consum Carburanti", "tone GPL", Carrier.lpg, "t"),
        ("Consum Carburanti", "1 t (CTL", Carrier.ctl, "t"),
        ("Consum electrica fotovoltaic", "1 MWh", Carrier.electricity_pv, "MWh"),
        ("energi electrica din cogenerar", "1 MWh", Carrier.electricity_cogen, "MWh"),
        ("Consum Cocs", "1 tona", Carrier.coke, "t"),
        ("Consum Cocs", "1 MWh", Carrier.coke, "MWh"),
        ("Consum Coji floarea soarelui", "1 Gcal", Carrier.sunflower_husks, "Gcal"),
        ("Consum Energie termica terti", "1 Gcal", Carrier.purchased_heat, "Gcal"),
    ):
        sheet = sheet_named(book, sheet_name, out.issues)
        if sheet is None or carrier not in out.dataset.carriers:
            continue
        candidates: list[Located] = []
        for row in range(1, sheet.max_row + 1):
            values = [cell_or_blank(sheet, row, col).value for col in range(1, sheet.max_col + 1)]
            label_columns = [
                index
                for index, value in enumerate(values)
                if isinstance(value, str)
                and normal(label).replace(" ", "") in normal(value).replace(" ", "")
            ]
            if not label_columns:
                continue
            equal = next(
                (col for col in range(min(label_columns) + 1, len(values)) if values[col] == "="),
                None,
            )
            if equal is not None and equal + 2 < len(values):
                factor_value = numeric(values[equal + 1])
                if factor_value is not None and normal(str(values[equal + 2])) == "tep":
                    candidates.append(Located(factor_value, CellRef(sheet.name, row, equal + 2)))
        if len(candidates) > 1:
            out.issues.append(
                ReaderIssue("factor_ambiguous", f"{carrier.value}.{unit}", candidates[0].ref)
            )
            continue
        if candidates:
            found = candidates[0]
            factor_value = numeric(found.value)
            assert factor_value is not None
            tep.append(Factor(carrier, unit, factor_value, f"{source_file}:{found.ref.a1}"))
            out.located[f"factor.tep.{carrier.value}.{unit}"] = found
            if carrier != Carrier.coke:
                out.located[f"factor.tep.{carrier.value}"] = found
    primary = sheet_named(book, "Principali factori de conversie", out.issues)
    if primary is not None:
        for carrier, needle in ((Carrier.petrol, "benzina"), (Carrier.electricity_pv, "electric")):
            if carrier not in out.dataset.carriers or any(f.carrier == carrier for f in tep):
                continue
            for row in range(1, primary.max_row + 1):
                if not any(
                    needle in normal(str(cell_or_blank(primary, row, col).value or ""))
                    for col in range(1, primary.max_col + 1)
                ):
                    continue
                for col in range(2, primary.max_col + 1):
                    if normal(str(cell_or_blank(primary, row, col).value or "")) != "tep":
                        continue
                    cell = cell_or_blank(primary, row, col - 1)
                    value = numeric(cell.value)
                    if value is not None:
                        unit = "MWh" if carrier == Carrier.electricity_pv else "t"
                        tep.append(Factor(carrier, unit, value, f"{source_file}:{cell.ref.a1}"))
                        out.located[f"factor.tep.{carrier.value}"] = located(cell, value)
                    break
                if any(f.carrier == carrier for f in tep):
                    break
    co2 = _co2_factors(book, years, out, source_file)
    return FactorTable(
        "prelucrare:import",
        min(years) if years else 1,
        tuple(tep),
        tuple(co2),
        valid_to_year=max(years) if years else 1,
    )


def _co2_factors(  # noqa: C901, PLR0912
    book: Book, years: tuple[int, ...], out: PrelucrareData, source_file: str
) -> list[Factor]:
    co2: list[Factor] = []
    impact = sheet_named(book, "impact de mediu", out.issues)
    if impact is not None:
        current_year: int | None = None
        last_fuel: Carrier | None = None
        for row in range(1, impact.max_row + 1):
            label = normal(str(cell_or_blank(impact, row, 2).value or ""))
            year = year_label(cell_or_blank(impact, row, 2).value)
            if year in years:
                current_year, last_fuel = year, None
            if current_year is None:
                continue
            carrier = carrier_for(label)
            if label == "carburant":
                carrier = Carrier.diesel
            elif not label and last_fuel == Carrier.diesel:
                carrier = Carrier.petrol
            elif not label and last_fuel == Carrier.petrol:
                carrier = Carrier.lpg
            if carrier is None:
                if label == "indicator global prin suprapunerea efectelor":
                    cell = cell_or_blank(impact, row, 9)
                    value = numeric(cell.value)
                    if value is not None:
                        out.filed[f"co2.total.{current_year}"] = located(cell, value, "t CO2")
                continue
            cell = cell_or_blank(impact, row, 9)
            value = numeric(cell.value)
            if value is None:
                continue
            out.filed[f"co2.{carrier.value}.{current_year}"] = located(cell, value, "t CO2")
            if carrier in {Carrier.diesel, Carrier.petrol, Carrier.lpg}:
                last_fuel = carrier
            factor_col = 6 if carrier in {Carrier.electricity_grid, Carrier.natural_gas} else 8
            factor_cell = cell_or_blank(impact, row, factor_col)
            factor = numeric(factor_cell.value)
            if factor is not None:
                factor_unit = "MWh" if factor_col == 6 else "t"
                co2.append(
                    Factor(
                        carrier,
                        factor_unit,
                        factor,
                        f"{source_file}:{factor_cell.ref.a1}",
                        current_year,
                    )
                )
                out.located[f"factor.co2.{carrier.value}.{current_year}"] = located(
                    factor_cell, factor
                )
    return co2
