"""Filed annex measures and the one permitted derived table value."""

from __future__ import annotations

from dataclasses import dataclass

from ema.energy_data.anexa_cells import AnexaData, Measure
from ema.energy_data.source import Located


@dataclass(frozen=True)
class MeasureRow:
    description: Located
    commissioning_year: Located | None
    location: Located | None
    values: dict[str, Located]
    payback_years: float | None
    payback_inputs: tuple[Located, Located] | None


def calculated_payback(measure: Measure) -> float | None:
    investment = measure.values.get("investment_thousand_lei")
    savings = measure.values.get("saving_thousand_lei")
    if (
        investment is not None
        and savings is not None
        and isinstance(investment.value, int | float)
        and isinstance(savings.value, int | float)
        and savings.value > 0
    ):
        return float(investment.value) / float(savings.value)
    return None


def _row(measure: Measure) -> MeasureRow:
    payback = calculated_payback(measure)
    investment = measure.values.get("investment_thousand_lei")
    savings = measure.values.get("saving_thousand_lei")
    inputs = (investment, savings) if payback is not None and investment and savings else None
    return MeasureRow(
        measure.description,
        measure.commissioning_year,
        measure.location,
        measure.values,
        payback,
        inputs,
    )


def payback_matches(measure: Measure, calculated: float) -> bool:
    """Compare the filed ratio with the rounding carried by each source cell."""
    filed = measure.values.get("payback_years")
    investment = measure.values.get("investment_thousand_lei")
    savings = measure.values.get("saving_thousand_lei")
    if (
        filed is None
        or investment is None
        or savings is None
        or not isinstance(filed.value, int | float)
        or not isinstance(investment.value, int | float)
        or not isinstance(savings.value, int | float)
    ):
        return False
    if any(item.displayed_decimals is None for item in (filed, investment, savings)):
        return float(filed.value) == calculated
    assert filed.displayed_decimals is not None
    assert investment.displayed_decimals is not None
    assert savings.displayed_decimals is not None
    cost_half = 0.5 * 10 ** (-investment.displayed_decimals)
    saving_half = 0.5 * 10 ** (-savings.displayed_decimals)
    filed_half = 0.5 * 10 ** (-filed.displayed_decimals)
    if savings.value <= saving_half:
        return False
    lower = (investment.value - cost_half) / (savings.value + saving_half)
    upper = (investment.value + cost_half) / (savings.value - saving_half)
    return lower <= filed.value + filed_half and upper >= filed.value - filed_half


def measures(anexa: AnexaData, *, planned: bool) -> tuple[MeasureRow, ...]:
    source = anexa.planned_measures if planned else anexa.existing_measures
    return tuple(_row(item) for item in source)
