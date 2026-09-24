"""Reconcile PIEE annual totals with the filed Anexa value."""

from __future__ import annotations

from dataclasses import dataclass

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
