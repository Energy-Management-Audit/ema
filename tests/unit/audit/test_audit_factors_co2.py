"""Issue #71: Measure CO₂ calculations use audit factors, not PIEE factors."""

from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import AUDIT_FACTORS_2026
from ema.energy_data.measure_calc import measure_co2


def test_measure_co2_uses_audit_factors() -> None:
    """100 MWh grid electricity → 17.2 t CO2 with AUDIT_FACTORS_2026."""
    electricity = Carrier.electricity_grid
    emissions = measure_co2(100, "MWh", electricity, 2025, AUDIT_FACTORS_2026)
    assert emissions.value == 17.2
    assert emissions.factor_version == "2026-audit"
