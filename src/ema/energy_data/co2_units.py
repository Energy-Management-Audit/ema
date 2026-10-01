"""Convert CO₂ factors through sourced tep factors when source units differ."""

from __future__ import annotations

from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import Derived


def converted_co2(
    carrier: Carrier,
    unit: str,
    amount: float,
    inputs: tuple[str, ...],
    factors: FactorTable,
    year: int,
) -> Derived | None:
    alternatives = [
        item
        for item in factors.co2
        if item.carrier == carrier and item.unit != unit and item.year in (None, year)
    ]
    if len(alternatives) != 1:
        return None
    other = alternatives[0]
    source_tep = factors.tep_factor(carrier, unit, year)
    other_tep = factors.tep_factor(carrier, other.unit, year)
    if (
        source_tep is None
        or other_tep is None
        or other_tep.per_unit <= 0
        or source_tep.source.rsplit("!", 1)[0] != other_tep.source.rsplit("!", 1)[0]
    ):
        return None
    ratio = source_tep.per_unit / other_tep.per_unit
    return Derived(
        amount * ratio * other.per_unit,
        "t CO₂",
        "t CO₂.unit_conversion",
        (
            *inputs,
            f"factor.tep.{carrier.value}.{unit}",
            f"factor.tep.{carrier.value}.{other.unit}",
            f"factor.co2.{carrier.value}.{year}",
        ),
        factors.version,
        input_weights=(
            *((ratio * other.per_unit,) * len(inputs)),
            amount * other.per_unit / other_tep.per_unit,
            -amount * source_tep.per_unit * other.per_unit / other_tep.per_unit**2,
            amount * ratio,
        ),
        year=year,
    )
