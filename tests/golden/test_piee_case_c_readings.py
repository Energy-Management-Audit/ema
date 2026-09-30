"""piee-case-c: level 2 source readings from the auditor's Prelucrare workbook."""

from __future__ import annotations

import pytest
from openpyxl import load_workbook
from tests.golden.cases import case_path

from ema.energy_data.anexa import parse_anexa
from ema.energy_data.calc import specific_consumption, tep, tep_total, water_specific
from ema.energy_data.carriers import Carrier
from ema.energy_data.prelucrare import import_prelucrare

pytestmark = pytest.mark.golden


def test_piee_case_c_source_series_and_cells() -> None:
    source = case_path("piee-case-c", "prelucrare")
    imported = import_prelucrare(source)
    book = load_workbook(source, read_only=True, data_only=True)
    assert imported.dataset.years == (2023, 2024, 2025)
    assert imported.dataset.production_unit == {"main": "tone"}
    rows = {
        Carrier.electricity_cogen: ("energi electrica din cogenerar ", (8, 12, 16)),
        Carrier.coke: ("Consum Cocs", (8, 12, 16)),
        Carrier.diesel: ("Consum Carburanti", (9, 19, 29)),
    }
    for carrier, (sheet_name, years_rows) in rows.items():
        sheet = book[sheet_name]
        for year, row in zip(imported.dataset.years, years_rows, strict=True):
            series = imported.dataset.carriers[carrier][year]
            unit = "t" if carrier == Carrier.diesel else "MWh"
            assert series.annual is not None
            assert series.annual.value == pytest.approx(sheet[f"Q{row}"].value)
            assert series.annual.unit == unit
            assert (
                imported.located[f"carrier.{carrier.value}.{year}"].ref.a1 == f"{sheet_name}!Q{row}"
            )
            for month in range(1, 13):
                column = month + 3
                assert series.months[month].value == pytest.approx(sheet.cell(row, column).value)
                assert imported.located[f"carrier.{carrier.value}.{year}.{month:02d}"].ref.a1 == (
                    f"{sheet_name}!{sheet.cell(row, column).coordinate}"
                )
    for year, monthly_row, annual_row in zip(
        imported.dataset.years, (7, 10, 13), (22, 23, 24), strict=True
    ):
        series = imported.dataset.production["main"][year]
        assert series.annual is not None
        assert series.annual.value == pytest.approx(book["Productii"][f"D{annual_row}"].value)
        assert imported.located[f"production.main.{year}"].ref.a1 == f"Productii!D{annual_row}"
        for month in range(1, 13):
            cell = book["Productii"].cell(monthly_row, month + 3)
            assert series.months[month].value == pytest.approx(cell.value)
            assert imported.located[f"production.main.{year}.{month:02d}"].ref.a1 == (
                f"Productii!{cell.coordinate}"
            )
        assert (
            specific_consumption(imported.dataset, imported.factors, year, None, "main").value
            is not None
        )

    water = {
        Carrier.water_potable: (4, 5, 6),
        Carrier.water_industrial: (28, 29, 30),
        Carrier.water_storm: (54, 55, 56),
    }
    for carrier, years_rows in water.items():
        for year, row in zip(imported.dataset.years, years_rows, strict=True):
            series = imported.dataset.carriers[carrier][year]
            assert series.annual is not None
            assert series.annual.value == pytest.approx(book["Consum apa "][f"O{row}"].value)
            assert series.annual.unit == "m3"
            assert (
                imported.located[f"carrier.{carrier.value}.{year}"].ref.a1 == f"Consum apa !O{row}"
            )
            for month in range(1, 13):
                cell = book["Consum apa "].cell(row, month + 2)
                assert series.months[month].value == pytest.approx(cell.value)
                assert imported.located[f"carrier.{carrier.value}.{year}.{month:02d}"].ref.a1 == (
                    f"Consum apa !{cell.coordinate}"
                )
            assert water_specific(imported.dataset, year, carrier, "main").value is not None


def test_piee_case_c_factors_and_annual_cross_check() -> None:
    imported = import_prelucrare(case_path("piee-case-c", "prelucrare"))
    anexa = parse_anexa(case_path("piee-case-c", "anexa"))
    for carrier, unit, factor, cell in (
        (Carrier.electricity_cogen, "MWh", 0.086, "F4"),
        (Carrier.coke, "t", 0.762, "F4"),
        (Carrier.coke, "MWh", 0.086, "F5"),
    ):
        actual = imported.factors.tep_factor(carrier, unit, 2025)
        assert actual is not None and actual.per_unit == factor
        assert actual.source.endswith(f"!{cell}")
        assert imported.located[f"factor.tep.{carrier.value}.{unit}"].ref.a1.endswith(cell)
    for carrier, raw_cell, tep_cell in (
        (Carrier.diesel, "E16", "E18"),
        (Carrier.coke, "F16", "F18"),
    ):
        series = imported.dataset.carriers[carrier][2025]
        assert series.annual is not None
        assert series.annual.value == pytest.approx(anexa.annual[f"{carrier.value}_raw"].value)
        assert anexa.annual[f"{carrier.value}_raw"].ref.a1 == f"Date anuale!{raw_cell}"
        assert tep(imported.dataset, imported.factors, carrier, 2025).value == pytest.approx(
            anexa.annual[f"{carrier.value}_tep"].value
        )
        assert anexa.annual[f"{carrier.value}_tep"].ref.a1 == f"Date anuale!{tep_cell}"
    assert tep_total(imported.dataset, imported.factors, 2025).value == pytest.approx(
        imported.filed["tep.total.2025"].value
    )
    assert tep(
        imported.dataset, imported.factors, Carrier.electricity_cogen, 2025
    ).value == pytest.approx(1108.009724)
