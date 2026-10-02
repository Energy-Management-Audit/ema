from __future__ import annotations

import pytest

from ema.energy_data.calc import (
    annual,
    change,
    co2,
    energy_intensity,
    shares,
    specific_consumption,
    tep,
    tep_total,
    trend,
)
from ema.energy_data.carriers import ALIASES, Carrier, carrier_for
from ema.energy_data.factors import FACTORS_2026, Factor, FactorTable
from ema.energy_data.model import CarrierSeries, Derived, EnergyDataset, Reading, field_key
from ema.energy_data.reconcile import reconcile


@pytest.mark.parametrize(("carrier", "labels"), ALIASES.items())
def test_aliases(carrier: Carrier, labels: tuple[str, ...]) -> None:
    for label in labels:
        assert carrier_for(label) == carrier
        assert carrier_for(f"  {label.upper()}  ") == carrier
    assert carrier_for("unknown future fuel") is None


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Gaze naturale", Carrier.natural_gas),
        ("Pacura", Carrier.fuel_oil),
        ("CLU", Carrier.clu),
        ("Benzina", Carrier.petrol),
        ("Motorina", Carrier.diesel),
        ("Carbune", Carrier.coal),
        ("Alti combustibili", None),
        ("GPL", Carrier.lpg),
        ("Lemn", Carrier.wood),
        ("Biomasa", Carrier.biomass),
        ("Carbune (cocs)", Carrier.coke),
        ("CTL", Carrier.ctl),
        ("Alti combustibili - GPL", Carrier.lpg),
    ],
)
def test_anexa_fuel_header_variants(header: str, expected: Carrier | None) -> None:
    assert carrier_for(header) == expected


def table(version: str = "v1", factor: float = 0.086) -> FactorTable:
    return FactorTable(
        version,
        2024,
        (Factor(Carrier.electricity_grid, "MWh", factor, "synthetic"),),
        (Factor(Carrier.electricity_grid, "MWh", 0.2, "synthetic"),),
    )


def dataset(series: CarrierSeries | None = None) -> EnergyDataset:
    carriers = {} if series is None else {Carrier.electricity_grid: {2024: series}}
    return EnergyDataset((2024,), carriers)


def test_annual_requires_every_month_unless_filed() -> None:
    series = CarrierSeries({1: Reading(10, "MWh")})
    result = annual(series, "carrier", Carrier.electricity_grid.value, 2024)
    assert result.value is None
    assert field_key("carrier", Carrier.electricity_grid.value, 2024, 2) in result.missing
    filed = annual(
        CarrierSeries(series.months, Reading(120, "MWh")),
        "carrier",
        Carrier.electricity_grid.value,
        2024,
    )
    assert filed.value == 120
    assert filed.formula_id == "annual.filed"


def test_annual_only_carrier_uses_filed_total_and_contributes_to_share() -> None:
    year = 2030
    pv = Carrier.electricity_pv
    factors = FactorTable(
        "synthetic",
        year,
        (
            Factor(pv, "MWh", 0.1, "synthetic"),
            Factor(Carrier.electricity_grid, "MWh", 0.1, "synthetic"),
        ),
        (),
    )
    ds = EnergyDataset(
        (year,),
        {
            pv: {year: CarrierSeries(annual=Reading(25, "MWh"))},
            Carrier.electricity_grid: {year: CarrierSeries(annual=Reading(75, "MWh"))},
        },
    )
    filed = annual(ds.carriers[pv][year], "carrier", pv.value, year)
    assert filed.formula_id == "annual.filed"
    assert tep(ds, factors, pv, year).value == pytest.approx(2.5)
    monthly = tep(ds, factors, pv, year, 1)
    assert monthly.value is None
    assert monthly.missing == (field_key("carrier", pv.value, year, 1),)
    assert shares(ds, factors, year)[pv].value == pytest.approx(25)


def test_absent_and_present_without_data_are_distinct() -> None:
    absent = tep(dataset(), table(), Carrier.electricity_grid, 2024)
    present = tep(dataset(CarrierSeries()), table(), Carrier.electricity_grid, 2024)
    assert absent.formula_id == "absent_carrier"
    assert absent.missing == ("carrier.electricity_grid.2024",)
    assert present.value is None and present.missing


def test_missing_factor_does_not_default() -> None:
    ds = EnergyDataset((2024,), {Carrier.diesel: {2024: CarrierSeries(annual=Reading(2, "l"))}})
    result = tep(ds, table(), Carrier.diesel, 2024)
    assert result.value is None
    assert result.missing == ("factor.tep.diesel.l.2024",)


def test_water_is_not_energy() -> None:
    ds = EnergyDataset(
        (2024,),
        {
            Carrier.water_potable: {2024: CarrierSeries(annual=Reading(10, "m3"))},
            Carrier.electricity_grid: {2024: CarrierSeries(annual=Reading(100, "MWh"))},
        },
    )
    assert tep(ds, table(), Carrier.water_potable, 2024).formula_id == "not_energy"
    assert co2(ds, table(), 2024, Carrier.water_potable).missing == ()
    assert tep_total(ds, table(), 2024).value == 8.6


def test_derived_remembers_factor_version() -> None:
    ds = dataset(CarrierSeries(annual=Reading(100, "MWh")))
    first = tep(ds, table(), Carrier.electricity_grid, 2024)
    second = tep(ds, table("v2", 0.1), Carrier.electricity_grid, 2024)
    assert first.value == 8.6 and first.factor_version == "v1"
    assert second.value == 10 and second.factor_version == "v2"
    assert first.value == 8.6


def test_zero_denominators_and_missing_values() -> None:
    missing = Derived(None, "tep", "tep.total", missing=("carrier.x.2023",), year=2023)
    zero = Derived(0, "tep", "tep.total", year=2023)
    current = Derived(10, "tep", "tep.total", year=2024)
    assert "previous.missing" in change(missing, current).missing
    assert "previous.zero" in change(zero, current).missing
    ds = dataset(CarrierSeries(annual=Reading(100, "MWh")))
    assert "turnover.2024" in energy_intensity(ds, table(), 2024).missing
    assert (
        shares(dataset(CarrierSeries(annual=Reading(0, "MWh"))), table(), 2024)[
            Carrier.electricity_grid
        ].value
        is None
    )


def test_specific_requires_declared_production_unit() -> None:
    ds = EnergyDataset(
        (2024,),
        {Carrier.electricity_grid: {2024: CarrierSeries(annual=Reading(100, "MWh"))}},
        {"main": {2024: CarrierSeries(annual=Reading(1000, "kWh"))}},
        {"main": "MWh"},
    )
    result = specific_consumption(ds, table(), 2024, None, "main")
    assert result.value is None
    assert "unit.production.main.2024.MWh" in result.missing


def test_non_finite_products_and_quotients_become_missing() -> None:
    ds = dataset(CarrierSeries(annual=Reading(1e308, "MWh")))
    converted = tep(ds, table(factor=1e308), Carrier.electricity_grid, 2024)
    assert converted.value is None
    assert "result.non_finite" in converted.missing
    tiny = EnergyDataset(
        (2024,),
        {Carrier.electricity_grid: {2024: CarrierSeries(annual=Reading(1e308, "MWh"))}},
        {"main": {2024: CarrierSeries(annual=Reading(1e-308, "MWh"))}},
        {"main": "MWh"},
        {2024: Reading(1e-308, "lei")},
    )
    assert "result.non_finite" in specific_consumption(tiny, table(), 2024, None, "main").missing
    assert "result.non_finite" in energy_intensity(tiny, table(), 2024).missing
    underflowed = EnergyDataset(
        tiny.years,
        tiny.carriers,
        tiny.production,
        tiny.production_unit,
        {2024: Reading(5e-324, "lei")},
    )
    assert "result.non_finite" in energy_intensity(underflowed, table(), 2024).missing
    assert Derived(float("nan"), "tep", "synthetic").missing == ("result.non_finite",)


def test_change_requires_consecutive_years() -> None:
    previous = Derived(10, "tep", "tep.total", year=2022)
    current = Derived(20, "tep", "tep.total", year=2024)
    result = change(previous, current)
    assert result.value is None
    assert "year.not_consecutive" in result.missing
    assert change(Derived(10, "tep", "tep.total", year=2023), current).value == 100


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([1, 2, 3], "creștere"),
        ([3, 2, 1], "scădere"),
        ([1, 1, 1], "constantă"),
        ([1.001, 1.002, 1.003], "constantă"),
        ([1, 2, 1], "constantă"),
    ],
)
def test_trend(values: list[float], expected: str) -> None:
    assert trend(values) == expected


def test_trend_uses_prototype_precision() -> None:
    assert trend([1.001, 1.002, 1.003], decimals=3) == "creștere"
    assert trend([1.005, 1.005, 1.004], decimals=2) == "scădere"


def test_reconciliation_propagates_input_and_filed_rounding() -> None:
    total = Derived(10.0, "tep", "tep.total", ("a", "b"), input_weights=(2, 1))
    assert reconcile(10.1, 1, total, (1, 1)).status == "match"
    assert reconcile(10.21, 1, total, (1, 1)).status == "conflict"
    assert reconcile(10.5, 0, Derived(10, "tep", "annual.sum"), ()).status == "match"


def test_field_keys_are_stable_and_unambiguous() -> None:
    key = field_key("carrier", "natural_gas", 2024, 3)
    assert key == "carrier.natural_gas.2024.03"
    kind, name, item_year, month = key.split(".")
    assert field_key(kind, name, int(item_year), int(month)) == key
    assert field_key("turnover", None, 2024) == "turnover.2024"
    with pytest.raises(ValueError):
        field_key("carrier", "natural_gas", 2024, 13)
    with pytest.raises(ValueError):
        field_key("production", "ambiguous.name", 2024)


def test_invalid_readings_and_year_order_are_rejected() -> None:
    with pytest.raises(ValueError):
        Reading(float("nan"), "MWh")
    with pytest.raises(ValueError):
        CarrierSeries({13: Reading(1, "MWh")})
    with pytest.raises(ValueError):
        EnergyDataset((2025, 2024), {})
    with pytest.raises(ValueError):
        trend([1, float("inf")])


def test_factor_year_precedence_and_validity() -> None:
    factors = FactorTable(
        "test",
        2024,
        (
            Factor(Carrier.natural_gas, "MWh", 0.08, "base"),
            Factor(Carrier.natural_gas, "MWh", 0.09, "revised", 2025),
        ),
        (),
    )
    assert factors.tep_factor(Carrier.natural_gas, "MWh", 2023) is None
    assert factors.tep_factor(Carrier.natural_gas, "MWh", 2024).per_unit == 0.08
    assert factors.tep_factor(Carrier.natural_gas, "MWh", 2025).per_unit == 0.09


def test_co2_total_stays_missing_without_carrier_factor() -> None:
    ds = EnergyDataset(
        (2024,),
        {
            Carrier.electricity_grid: {2024: CarrierSeries(annual=Reading(100, "MWh"))},
            Carrier.sunflower_husks: {2024: CarrierSeries(annual=Reading(20, "Gcal"))},
        },
    )
    result = co2(ds, table(), 2024)
    assert result.value is None
    assert "factor.co2.sunflower_husks.Gcal.2024" in result.missing


@pytest.mark.parametrize("carrier", [Carrier.biomass, Carrier.sunflower_husks, Carrier.wood])
def test_biomass_co2_factor_is_zero_and_traceable(carrier: Carrier) -> None:
    ds = EnergyDataset((2025,), {carrier: {2025: CarrierSeries(annual=Reading(20, "Gcal"))}})

    factor = FACTORS_2026.co2_factor(carrier, "Gcal", 2025)
    result = co2(ds, FACTORS_2026, 2025, carrier)

    assert factor is not None and factor.per_unit == 0
    assert "2018/2066" in factor.source
    assert result.value == 0
    assert result.inputs == ("carrier." + carrier.value + ".2025",)


def test_monthly_co2_uses_monthly_reading() -> None:
    ds = dataset(CarrierSeries({1: Reading(5, "MWh")}, Reading(100, "MWh")))
    assert co2(ds, table(), 2024, Carrier.electricity_grid, 1).value == 1.0
    assert co2(ds, table(), 2024, Carrier.electricity_grid, 2).value is None
