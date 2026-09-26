"""Measure conversions use the 2026 table and her TRB equation."""

from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.measure_calc import measure_co2, measure_tep, payback_years


def test_energy_emissions_and_factor_gaps() -> None:
    electricity = Carrier.electricity_grid
    assert measure_tep(100, "MWh", electricity, 2025, FACTORS_2026).value == 8.6
    emissions = measure_co2(100, "MWh", electricity, 2025, FACTORS_2026)
    assert emissions.value == 22.6
    assert (emissions.formula_id, emissions.inputs, emissions.factor_version) == (
        "audit_measure.co2",
        ("saving_amount",),
        "2026",
    )
    assert measure_co2(8.6, "tep", electricity, 2025, FACTORS_2026).value == 22.6
    assert measure_co2(1.015, "tep", Carrier.diesel, 2025, FACTORS_2026).value == 3.259
    missing = measure_co2(1, "MWh", Carrier.electricity_pv, 2025, FACTORS_2026)
    assert missing.value is None and missing.missing == ("factor.co2.electricity_pv.MWh.2025",)
    assert measure_tep(1, "t", Carrier.wood, 2025, FACTORS_2026).value is None


def test_trb_missing_cost_is_not_derived() -> None:
    result = payback_years(40, 10)
    assert (result.value, result.formula_id, result.inputs) == (
        4,
        "audit_measure.trb",
        ("investment_thousand_lei", "cost_saving_thousand_lei"),
    )
    for cost in (None, 0):
        assert payback_years(40, cost).value is None
    assert payback_years(None, 10).value is None
