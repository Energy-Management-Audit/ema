"""Synthetic precedence, unit conversion, and factor coverage checks."""

from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026, FactorTable
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading
from ema.energy_data.prelucrare_merge import merge_prelucrare
from ema.energy_data.prelucrare_types import PrelucrareData


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
