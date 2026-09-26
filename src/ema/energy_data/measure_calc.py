"""Sourced, unrounded energy, emissions and TRB for one proposed measure."""

from __future__ import annotations

from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import Derived


def measure_tep(
    amount: float | None, unit: str, carrier: Carrier, year: int, factors: FactorTable
) -> Derived:
    factor = factors.tep_factor(carrier, unit, year)
    missing = (
        ("saving_amount",)
        if amount is None
        else (f"factor.tep.{carrier.value}.{unit}.{year}",)
        if factor is None
        else ()
    )
    return Derived(
        amount * factor.per_unit if amount is not None and factor is not None else None,
        "tep",
        "audit_measure.tep",
        ("saving_amount",),
        factors.version,
        missing,
        year=year,
    )


def measure_co2(
    amount: float | None, unit: str, carrier: Carrier, year: int, factors: FactorTable
) -> Derived:
    selected = unit
    if unit == "tep":
        selected = (
            "MWh"
            if carrier
            in {
                Carrier.electricity_grid,
                Carrier.electricity_pv,
                Carrier.natural_gas,
            }
            else "t"
        )
    co2 = factors.co2_factor(carrier, selected, year)
    tep = factors.tep_factor(carrier, selected, year) if unit == "tep" else None
    missing = (
        ("saving_amount",)
        if amount is None
        else (f"factor.co2.{carrier.value}.{selected}.{year}",)
        if co2 is None
        else (f"factor.tep.{carrier.value}.{selected}.{year}",)
        if unit == "tep" and (tep is None or tep.per_unit == 0)
        else ()
    )
    weight = (
        co2.per_unit / tep.per_unit
        if co2 and tep and tep.per_unit
        else co2.per_unit
        if co2
        else None
    )
    return Derived(
        amount * weight if amount is not None and weight is not None and not missing else None,
        "t CO₂",
        "audit_measure.co2",
        ("saving_amount",),
        factors.version,
        missing,
        year=year,
    )


def payback_years(investment: float | None, cost_saving: float | None) -> Derived:
    missing = (
        ("investment_thousand_lei",)
        if investment is None
        else ("cost_saving_thousand_lei",)
        if cost_saving is None or cost_saving == 0
        else ()
    )
    return Derived(
        investment / cost_saving if investment is not None and cost_saving else None,
        "ani",
        "audit_measure.trb",
        ("investment_thousand_lei", "cost_saving_thousand_lei"),
        missing=missing,
    )
