"""Metric resolution does not invent missing totals or combine unlike units."""

import pytest

from ema.consumption_analysis.analysis import Metric, resolve_value
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import CarrierSeries, EnergyDataset, FiledValue, Reading


def _dataset(*, complete: bool = True) -> EnergyDataset:
    return EnergyDataset(
        (2025,),
        {
            Carrier.electricity_grid: {2025: CarrierSeries(annual=Reading(10, "MWh"))},
            Carrier.diesel: {2025: CarrierSeries(annual=Reading(2, "t"))},
        },
        filed_indicators={"tep_total": {2025: FiledValue(3, "tep", 2, "synthetic filing")}},
        energy_inventory_complete=complete,
    )


def test_complete_total_prefers_calculation_and_reports_filing_conflict() -> None:
    result = resolve_value(_dataset(), FACTORS_2026, Metric("tep_total"), 2025)
    assert result.value == pytest.approx(10 * 0.086 + 2 * 1.015)
    assert result.origin == "recomputed"
    assert result.conflict


def test_incomplete_inventory_uses_explicit_filing() -> None:
    result = resolve_value(_dataset(complete=False), FACTORS_2026, Metric("tep_total"), 2025)
    assert result.value == 3
    assert result.origin == "filed"
    assert not result.conflict


def test_missing_month_and_unlike_units_are_not_combined() -> None:
    dataset = _dataset()
    missing = resolve_value(
        dataset, FACTORS_2026, Metric("carrier", (Carrier.diesel,), month=1), 2025
    )
    assert missing.value is None and missing.origin == "missing"
    with pytest.raises(ValueError, match="different units"):
        resolve_value(
            dataset,
            FACTORS_2026,
            Metric("carrier", (Carrier.electricity_grid, Carrier.diesel)),
            2025,
        )
    with pytest.raises(ValueError, match="outside the dataset"):
        resolve_value(dataset, FACTORS_2026, Metric("tep_total"), 2024)


@pytest.mark.parametrize(
    "metric,message",
    [
        (Metric("production"), "needs a product"),
        (Metric("carrier"), "at least one carrier"),
        (Metric("specific"), "needs a product"),
        (Metric("water_specific"), "needs a product and water carrier"),
        (Metric("tep"), "needs one carrier"),
    ],
)
def test_invalid_metric_inputs_are_rejected(metric: Metric, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_value(_dataset(), FACTORS_2026, metric, 2025)
