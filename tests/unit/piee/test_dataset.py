"""PIEE source policy and annual filing checks on synthetic values."""

from __future__ import annotations

import pytest

from ema.core.errors import EmaError
from ema.core.office.sheets import CellRef
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import Factor, FactorTable
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading
from ema.energy_data.necesar_model import Consumption, NecesarInfo, YearValues
from ema.energy_data.prelucrare_types import PrelucrareData
from ema.energy_data.source import Located
from ema.piee.dataset import assemble


def _source(sheet: str, value: float, unit: str | None = None, decimals: int | None = 3) -> Located:
    return Located(value, CellRef(sheet, 1, 1), unit, displayed_decimals=decimals)


def _inputs(filed: float) -> tuple[AnexaData, NecesarInfo]:
    anexa = AnexaData(year=_source("Date anuale", 2025, decimals=0))
    anexa.annual["total_tep"] = _source("Date anuale", filed, "tep/an")
    anexa.annual["electricity_grid_mwh"] = _source("Date anuale", 1.0, "MWh")
    necesar = NecesarInfo()
    necesar.carriers[Carrier.electricity_grid] = Consumption(
        _source("Cons energetice", 1.0),
        {2025: YearValues((None,) * 12, _source("Cons energetice", 1.0, "MWh"))},
    )
    return anexa, necesar


def test_date_anuale_rounding_match_and_conflict() -> None:
    matching = assemble(2025, *_inputs(0.086))
    assert matching.annual_check.status == "match"
    assert matching.annual_check.result is not None
    assert not matching.disagreements
    conflict = assemble(2025, *_inputs(0.09))
    assert conflict.annual_check.status == "conflict"


def test_unknown_precision_uses_exact_comparison_and_reports_it() -> None:
    anexa, necesar = _inputs(0.086)
    anexa.annual["total_tep"] = _source("Date anuale", 0.086, "tep/an", None)
    checked = assemble(2025, anexa, necesar).annual_check
    assert checked.status == "match"
    assert checked.unknown_precision == ("filed",)


def test_necesar_wins_over_annex_alternative() -> None:
    anexa, necesar = _inputs(0.086)
    anexa.annual["electricity_grid_mwh"] = _source("Date anuale", 2.0, "MWh")
    result = assemble(2025, anexa, necesar)
    assert len(result.disagreements) == 1
    assert result.disagreements[0].chosen_source == "necesar"
    assert result.disagreements[0].alternative_location is anexa.annual["electricity_grid_mwh"]
    assert result.dataset.carriers[Carrier.electricity_grid][2025].annual is not None
    assert result.dataset.carriers[Carrier.electricity_grid][2025].annual.value == 1.0


def test_annex_annual_unit_suffix_is_equivalent_but_value_difference_is_not() -> None:
    anexa, necesar = _inputs(0.086)
    necesar.carriers[Carrier.diesel] = Consumption(
        _source("Cons energetice", 1.0),
        {2025: YearValues((None,) * 12, _source("Cons energetice", 1.0, "t"))},
    )
    anexa.annual["diesel_raw"] = _source("Date anuale", 1.0, " t / an ")
    assert not any(
        item.key == "carrier.diesel.2025" for item in assemble(2025, anexa, necesar).disagreements
    )
    anexa.annual["diesel_raw"] = _source("Date anuale", 1.01, " t / an ")
    assert any(
        item.key == "carrier.diesel.2025" for item in assemble(2025, anexa, necesar).disagreements
    )
    anexa.annual["diesel_raw"] = _source("Date anuale", 1.0, "Gcal/an")
    assert any(
        item.key == "carrier.diesel.2025" for item in assemble(2025, anexa, necesar).disagreements
    )


def test_annex_annual_fills_gap_without_erasing_necesar_months() -> None:
    anexa, necesar = _inputs(0.086)
    months = (_source("Cons energetice", 1.0, "MWh"),) + (None,) * 11
    necesar.carriers[Carrier.electricity_grid].years[2025] = YearValues(months, None)
    result = assemble(2025, anexa, necesar)
    series = result.dataset.carriers[Carrier.electricity_grid][2025]
    assert series.annual is not None and series.annual.value == 1.0
    assert series.months[1].value == 1.0


def test_prelucrare_covering_analysis_years_exempts_necesar() -> None:
    anexa, _ = _inputs(0.086)
    imported = PrelucrareData(EnergyDataset((2023, 2024, 2025), {}), FactorTable("test", 1, (), ()))
    result = assemble(2025, anexa, None, imported)
    assert result.necesar_status == "not needed: covered by Prelucrare (years 2023, 2024, 2025)"


def test_missing_necesar_requires_full_prelucrare_period() -> None:
    anexa, _ = _inputs(0.086)
    imported = PrelucrareData(EnergyDataset((2024, 2025), {}), FactorTable("test", 1, (), ()))
    with pytest.raises(EmaError) as error:
        assemble(2025, anexa, None, imported)
    assert error.value.code == "piee_sources_incomplete"


@pytest.mark.parametrize("filed_tep, conflict", [(1.0, False), (2.0, True)])
def test_biomass_family_aggregate_is_evidence_not_second_carrier(
    filed_tep: float, conflict: bool
) -> None:
    anexa, necesar = _inputs(1.086)
    anexa.annual["biomass_raw"] = _source("Date anuale", 1.0, "u.m. / an")
    anexa.annual["biomass_tep"] = _source("Date anuale", filed_tep, "tep")
    imported = PrelucrareData(
        EnergyDataset(
            (2025,),
            {Carrier.sunflower_husks: {2025: CarrierSeries(annual=Reading(1.0, "Gcal"))}},
        ),
        FactorTable("filed", 2025, (Factor(Carrier.sunflower_husks, "Gcal", 1.0, "fixture"),), ()),
    )
    result = assemble(2025, anexa, necesar, imported)
    assert Carrier.biomass not in result.dataset.carriers
    assert Carrier.sunflower_husks in result.dataset.carriers
    assert (
        any(item.key == "carrier_family.biomass.2025" for item in result.disagreements) == conflict
    )
