"""Synthetic chart bindings preserve missing data and reviewed filed values."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from tests.workspace_jobs import register_client

from ema.core.office.sheets import CellRef
from ema.core.review import fields
from ema.core.workspace import Workspace
from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading
from ema.energy_data.necesar_model import Consumption, NecesarInfo, YearValues
from ema.energy_data.prelucrare_types import PrelucrareData
from ema.energy_data.source import Located
from ema.piee.annual_check import AnnualCheck
from ema.piee.chart_plan import BINDINGS, ChartBinding, chart_series
from ema.piee.dataset import PieeData
from ema.piee.extra_figures import _annual_fuel, _biomass, _specific_mix
from ema.piee.intake import import_piee
from ema.piee.pies import _mix, _pv, expanded_mix
from ema.piee.tables import _equivalent, _monthly


def _data() -> PieeData:
    years = (2023, 2024, 2025)

    def annual(number: float, unit: str) -> CarrierSeries:
        return CarrierSeries(annual=Reading(number, unit))

    dataset = EnergyDataset(
        years,
        {
            Carrier.electricity_grid: {
                year: CarrierSeries({1: Reading(10, "MWh")}, Reading(100, "MWh")) for year in years
            },
            Carrier.electricity_pv: {2025: annual(20, "MWh")},
            Carrier.natural_gas: {2025: annual(50, "MWh")},
            Carrier.diesel: {2025: CarrierSeries({1: Reading(2, "t")}, Reading(2, "t"))},
        },
        {
            "output": {
                year: CarrierSeries({1: Reading(100, "t")}, Reading(1000, "t")) for year in years
            }
        },
        {"output": "t"},
        {2025: Reading(10_000, "lei")},
    )
    necessary = NecesarInfo()
    location = Located("water", CellRef("Water", 1, 1))
    necessary.water[Carrier.water_potable] = Consumption(
        location,
        {
            2025: YearValues(
                (Located(3, CellRef("Water", 2, 1)),) + (None,) * 11,
                Located(30, CellRef("Water", 2, 14)),
            )
        },
    )
    filed = PrelucrareData(dataset, FACTORS_2026)
    filed.filed["tep.total.2025"] = Located(42, CellRef("Filed", 1, 1))
    filed.filed["co2.total.2025"] = Located(12, CellRef("Filed", 2, 1))
    return PieeData(
        2025,
        AnexaData(),
        necessary,
        filed,
        dataset,
        FACTORS_2026,
        (),
        AnnualCheck("missing", None, None),
    )


def test_monthly_and_annual_charts_keep_gaps_and_source_values() -> None:
    data = _data()
    production = chart_series(data, BINDINGS[0])[0]
    assert production is not None
    assert production.categories[0] == " Ianuarie "
    assert production.values == [100] + [None] * 11

    electricity = chart_series(data, ChartBinding("grid", "carrier", Carrier.electricity_grid))[0]
    assert electricity is not None
    assert electricity.values == [100, 100, 100]
    assert chart_series(data, ChartBinding("pv", "carrier", Carrier.electricity_pv))[0].values == [
        None,
        None,
        20,
    ]
    assert chart_series(data, ChartBinding("water", "water", Carrier.water_potable))[0].values == [
        None,
        None,
        30,
    ]
    assert chart_series(data, ChartBinding("tep", "total_tep"))[0].values[-1] == 42
    assert chart_series(data, ChartBinding("co2", "co2"))[0].values[-1] == 12


def test_missing_figures_and_fuel_series_are_explicit() -> None:
    data = _data()
    fuel = chart_series(data, ChartBinding("fuel", "fuel", year_offset=0))
    assert len(fuel) == 3
    assert fuel[0] is not None and fuel[0].values[0] == 2
    assert fuel[1:] == (None, None)
    assert chart_series(data, ChartBinding("share", "energy_share")) == (None,)
    hidden_pv = replace(data, layout=replace(data.layout, separate_pv_figures=False))
    assert chart_series(hidden_pv, ChartBinding("pv", "carrier", Carrier.electricity_pv)) == (None,)


def test_pie_shares_use_only_present_sourced_carriers() -> None:
    data = _data()
    assert _pv(data, 2025) == pytest.approx((100 / 120, 20 / 120))
    assert _pv(data, 2024) is None
    assert _pv(replace(data, layout=replace(data.layout, separate_pv_figures=False)), 2025) is None
    assert _pv(replace(data, pie_representation="raw"), 2025) == (100, 20)

    mix = _mix(data, 2025)
    assert mix is not None and sum(mix) == pytest.approx(1)
    assert _mix(data, 2024) is None
    expanded = expanded_mix(data, 2025)
    assert expanded is not None
    labels, values = expanded
    assert labels == ("Gaz", "Energie electrică", "Carburant", "Energie electrică fotovoltaică")
    assert values == pytest.approx((4.3, 8.6, 2.03, 1.72))


def test_table_and_extra_figure_values_keep_missing_months() -> None:
    data = _data()
    assert _monthly(data, 7) == [10] + [None] * 11
    assert _monthly(data, 17) == [None] * 12
    assert _equivalent(data, 2025) == pytest.approx((10.32, 4.3, 2.03, 42))
    assert _equivalent(data, 2024)[1:3] == (None, None)
    assert [series.name for series in _annual_fuel(data)] == ["Motorină"]
    assert _biomass(data) is None
    specific = _specific_mix(data, 2025)
    assert specific is not None
    assert specific.values == pytest.approx([0.0043, 0.0086, 0.00203, 0.00172])


def test_intake_records_located_sources_and_flags_unlocated_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _data()
    identity = Located("Synthetic Client", CellRef("Anexa", 2, 1))
    data.anexa.identity["name"] = identity
    data.anexa.annual["total_tep"] = Located(42, CellRef("Anexa", 3, 2), "tep")
    data.necesar.carriers[Carrier.electricity_grid] = Consumption(
        Located("Electric", CellRef("Necesar", 1, 1)),
        {
            2025: YearValues(
                (Located(10, CellRef("Necesar", 2, 1), "MWh"),) + (None,) * 11,
                Located(100, CellRef("Necesar", 2, 14), "MWh"),
            )
        },
    )
    data = replace(data, annual_check=AnnualCheck("match", data.anexa.annual["total_tep"], None))
    monkeypatch.setattr("ema.piee.intake.load", lambda *args: data)
    anexa = tmp_path / "anexa.xlsx"
    necesar = tmp_path / "necesar.xls"
    prelucrare = tmp_path / "prelucrare.xlsx"
    for path in (anexa, necesar, prelucrare):
        path.write_bytes(b"synthetic source")
    workspace = Workspace(tmp_path / "workspace")
    register_client(workspace, "synthetic")
    job = import_piee(workspace, "synthetic", 2025, anexa, necesar, prelucrare)
    assert [
        workspace.list_versions(job.id, slot)[0].original_name
        for slot in ("anexa", "questionnaire", "prelucrare")
    ] == ["anexa.xlsx", "necesar.xls", "prelucrare.xlsx"]
    found = {field.key: field for field in fields(workspace, job.id)}
    assert found["identity.name"].value == "Synthetic Client"
    assert found["carrier.electricity_grid.2025.01"].value == Decimal("10")
    assert found["annual.total_tep"].value == Decimal("42")
    assert found["carrier.natural_gas.2025"].failure is not None
    assert found["identity.name"].evidence
    assert not found["carrier.natural_gas.2025"].evidence
