"""Synthetic precedence, unit conversion, and factor coverage checks."""

from pathlib import Path

import pytest
from openpyxl import Workbook

from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026, Factor, FactorTable
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading
from ema.energy_data.prelucrare import import_prelucrare
from ema.energy_data.prelucrare_factors import factors_for_output
from ema.energy_data.prelucrare_merge import merge_prelucrare
from ema.energy_data.prelucrare_types import PrelucrareData


@pytest.mark.parametrize("prefix", ("Producția de", "Productia de", "Producţia de"))
def test_production_name_follows_shifted_label_with_cell_evidence(
    tmp_path: Path, prefix: str
) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Productii"
    sheet["E6"] = "Productie"
    sheet["G6"] = f"{prefix} Test Product"
    path = tmp_path / "prelucrare.xlsx"
    book.save(path)
    imported = import_prelucrare(path)
    assert imported.dataset.production_name == {"main": "Test Product"}
    assert imported.located["production_name.main"].ref.a1 == "Productii!G6"


def test_necesar_production_name_wins_over_prelucrare() -> None:
    other = EnergyDataset((2025,), {}, production_name={"main": "Necesar Product"})
    chosen = EnergyDataset((2025,), {}, production_name={"main": "Prelucrare Product"})
    merged, _ = merge_prelucrare(other, PrelucrareData(chosen, FACTORS_2026))
    assert merged.production_name == {"main": "Necesar Product"}


def test_factor_coverage_is_bounded_to_document_data_years() -> None:
    for year in (2023, 2024, 2025):
        assert FACTORS_2026.tep_factor(Carrier.natural_gas, "MWh", year) is not None
    assert FACTORS_2026.tep_factor(Carrier.natural_gas, "MWh", 2022) is None
    assert FACTORS_2026.tep_factor(Carrier.natural_gas, "MWh", 2026) is None
    assert FACTORS_2026.tep_factor(Carrier.lpg, "t", 2025) is None


def test_prelucrare_wins_with_conflict_and_production_unit_conversion() -> None:
    other = EnergyDataset(
        (2025,),
        {Carrier.natural_gas: {2025: CarrierSeries({1: Reading(20, "MWh")})}},
        {"gaze_vehiculate_productie": {2025: CarrierSeries({1: Reading(1_000_000, "kWh")})}},
        {"gaze_vehiculate_productie": "kWh"},
    )
    chosen = EnergyDataset(
        (2025,),
        {Carrier.natural_gas: {2025: CarrierSeries({1: Reading(21, "MWh")})}},
        {"main": {}},
        {"main": "mii MWh gaz vehiculat"},
    )
    imported = PrelucrareData(chosen, FactorTable("case", 2025, (), ()))
    merged, conflicts = merge_prelucrare(other, imported)
    assert merged.carriers[Carrier.natural_gas][2025].months[1].value == 21
    assert len(conflicts) == 1
    assert conflicts[0].field == "carrier.natural_gas.2025.01"
    assert conflicts[0].other.value == 20
    assert merged.production["main"][2025].months[1] == Reading(1, "mii MWh gaz vehiculat")


def test_annual_source_units_ignore_only_per_year_suffix() -> None:
    other = EnergyDataset(
        (2025,),
        {Carrier.diesel: {2025: CarrierSeries(annual=Reading(1, "t / an"))}},
    )
    chosen = EnergyDataset(
        (2025,),
        {Carrier.diesel: {2025: CarrierSeries(annual=Reading(1, "t"))}},
    )
    factors = FactorTable("case", 2025, (), ())
    assert not merge_prelucrare(other, PrelucrareData(chosen, factors))[1]
    different = EnergyDataset(
        (2025,),
        {Carrier.diesel: {2025: CarrierSeries(annual=Reading(1, "MWh/an"))}},
    )
    assert [
        item.field for item in merge_prelucrare(other, PrelucrareData(different, factors))[1]
    ] == ["carrier.diesel.2025"]


def test_output_factors_use_filed_years_and_documented_defaults_elsewhere() -> None:
    imported = PrelucrareData(
        EnergyDataset((2025,), {}),
        FactorTable("case", 2025, (Factor(Carrier.natural_gas, "MWh", 0.1, "source"),), ()),
    )
    output = factors_for_output(imported, (2024, 2025))
    assert output.tep_factor(Carrier.natural_gas, "MWh", 2024).per_unit == 0.086
    assert output.tep_factor(Carrier.natural_gas, "MWh", 2025).per_unit == 0.1
    assert output.tep_factor(Carrier.electricity_pv, "MWh", 2025).per_unit == 0.086
    assert output.co2_factor(Carrier.electricity_grid, "MWh", 2024).per_unit == 0.226
    assert output.co2_factor(Carrier.electricity_grid, "MWh", 2025) is None
