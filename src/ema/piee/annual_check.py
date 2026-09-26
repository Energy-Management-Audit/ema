"""Reconcile PIEE annual totals with the filed Anexa value, and months with annual readings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.calc import tep_total
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import Derived, EnergyDataset
from ema.energy_data.reconcile import Reconciliation, reconcile
from ema.energy_data.source import Located


@dataclass(frozen=True)
class AnnualCheck:
    status: str
    filed: Located | None
    result: Reconciliation | None
    unknown_precision: tuple[str, ...] = ()


def annual_check(
    anexa: AnexaData,
    year: int,
    dataset: EnergyDataset,
    factors: FactorTable,
    locations: dict[str, Located],
    chosen_total: Located | None,
) -> AnnualCheck:
    filed = anexa.annual.get("total_tep")
    if filed is None or not isinstance(filed.value, int | float):
        return AnnualCheck("missing", filed, None)
    if chosen_total is not None and isinstance(chosen_total.value, int | float):
        derived = Derived(
            float(chosen_total.value),
            "tep",
            "tep.prelucrare.filed",
            (f"tep.total.{year}",),
            input_weights=(1.0,),
            year=year,
        )
        locations = {**locations, f"tep.total.{year}": chosen_total}
    else:
        derived = tep_total(dataset, factors, year)
    if derived.value is None:
        return AnnualCheck("missing_inputs", filed, None)
    unknown = tuple(
        key
        for key in derived.inputs
        if key not in locations or locations[key].displayed_decimals is None
    )
    if filed.displayed_decimals is None or unknown:
        status = "match" if float(filed.value) == derived.value else "conflict"
        missing_precision = ("filed",) if filed.displayed_decimals is None else ()
        return AnnualCheck(status, filed, None, (*unknown, *missing_precision))
    checked = reconcile(
        float(filed.value),
        filed.displayed_decimals,
        derived,
        [locations[key].displayed_decimals or 0 for key in derived.inputs],
    )
    return AnnualCheck(checked.status, filed, checked)


@dataclass(frozen=True)
class MonthsMismatch:
    annual_key: str
    months_sum: Decimal
    annual: Decimal
    margin: Decimal


def _half_unit(value: Decimal) -> Decimal:
    exponent = value.as_tuple().exponent
    return Decimal("0.5").scaleb(min(int(exponent), 0) if isinstance(exponent, int) else 0)


def months_check(readings: Mapping[str, tuple[Decimal, str | None]]) -> list[MonthsMismatch]:
    """Per carrier and year with all 12 months, the months' sum against the filed annual reading.

    `readings` maps `carrier.<c>.<y>[.<MM>]` to the value in effect after review (a rejected
    reading is absent). The margin is half a unit of every figure's written precision.
    """
    months: dict[str, dict[int, tuple[Decimal, str | None]]] = {}
    for key, reading in readings.items():
        parts = key.split(".")
        if len(parts) == 4 and parts[0] == "carrier" and parts[3].isdigit():
            months.setdefault(".".join(parts[:3]), {})[int(parts[3])] = reading
    found: list[MonthsMismatch] = []
    for annual_key, by_month in sorted(months.items()):
        annual = readings.get(annual_key)
        if annual is None or set(by_month) != set(range(1, 13)):
            continue
        if any(unit != annual[1] for _, unit in by_month.values()):
            continue
        total = sum((value for value, _ in by_month.values()), Decimal(0))
        margin = _half_unit(annual[0]) + sum(
            (_half_unit(value) for value, _ in by_month.values()), Decimal(0)
        )
        if abs(total - annual[0]) > margin:
            found.append(MonthsMismatch(annual_key, total, annual[0], margin))
    return found
