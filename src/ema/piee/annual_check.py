"""Reconcile PIEE annual totals with the filed Anexa value, and months with annual readings."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from ema.energy_data.anexa_cells import AnexaData
from ema.energy_data.calc import tep, tep_total
from ema.energy_data.carriers import FAMILY_PARENT, Carrier, counts_in_total
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
    missing_carriers: tuple[str, ...] = ()
    unfiled_carriers: tuple[str, ...] = ()
    years: tuple[YearCheck, ...] = ()


@dataclass(frozen=True)
class FiledCheck:
    key: str
    filed: Located
    computed: Derived
    source: str
    status: str
    result: Reconciliation | None
    unknown_precision: tuple[str, ...] = ()


@dataclass(frozen=True)
class YearCheck:
    year: int
    missing_carriers: tuple[Carrier, ...]
    unfiled_carriers: tuple[Carrier, ...]
    components: tuple[FiledCheck, ...]
    totals: tuple[FiledCheck, ...]


def compare_filed(
    key: str, filed: Located, computed: Derived, locations: dict[str, Located], source: str
) -> FiledCheck:
    if not isinstance(filed.value, int | float):
        raise ValueError(f"numeric filing required: {key}")
    if computed.value is None:
        return FiledCheck(key, filed, computed, source, "missing_inputs", None)
    unknown = tuple(
        input_key
        for input_key in computed.inputs
        if input_key not in locations or locations[input_key].displayed_decimals is None
    )
    if filed.displayed_decimals is None or unknown:
        status = (
            "match"
            if math.isclose(float(filed.value), computed.value, rel_tol=1e-9, abs_tol=1e-9)
            else "conflict"
        )
        missing_precision = ("filed",) if filed.displayed_decimals is None else ()
        return FiledCheck(
            key, filed, computed, source, status, None, (*unknown, *missing_precision)
        )
    checked = reconcile(
        float(filed.value),
        filed.displayed_decimals,
        computed,
        [locations[input_key].displayed_decimals or 0 for input_key in computed.inputs],
    )
    return FiledCheck(key, filed, computed, source, checked.status, checked)


def annual_check(  # noqa: C901, PLR0912
    anexa: AnexaData,
    year: int,
    dataset: EnergyDataset,
    factors: FactorTable,
    locations: dict[str, Located],
    prelucrare_filed: dict[str, Located] | None,
) -> AnnualCheck:
    filed = anexa.annual.get("total_tep")
    filed_values = prelucrare_filed or {}
    yearly: list[YearCheck] = []
    for current_year in range(year - 2, year + 1):
        source_components: dict[Carrier, list[tuple[str, Located, str]]] = {}
        for carrier in Carrier:
            if not counts_in_total(carrier):
                continue
            selected = filed_values.get(f"tep.{carrier.value}.{current_year}")
            if (
                selected is not None
                and isinstance(selected.value, int | float)
                and selected.value != 0
            ):
                source_components.setdefault(carrier, []).append(
                    (f"tep.carrier.{carrier.value}.{current_year}", selected, "prelucrare_filed")
                )
            if current_year == year:
                annex = anexa.annual.get(f"{carrier.value}_tep")
                family_subtypes = [
                    sub for sub, parent in FAMILY_PARENT.items() if parent == carrier
                ]
                if any(current_year in dataset.carriers.get(sub, {}) for sub in family_subtypes):
                    continue
                if annex is not None and isinstance(annex.value, int | float) and annex.value != 0:
                    source_components.setdefault(carrier, []).append(
                        (f"anexa.tep.{carrier.value}.{current_year}", annex, "anexa")
                    )
        present = {
            carrier
            for carrier, years in dataset.carriers.items()
            if counts_in_total(carrier)
            and (series := years.get(current_year)) is not None
            and (
                (series.annual is not None and series.annual.value is not None)
                or any(reading.value is not None for reading in series.months.values())
            )
        }
        filed_carriers = set(source_components)
        components = tuple(
            compare_filed(
                key, selected, tep(dataset, factors, carrier, current_year), locations, source
            )
            for carrier in sorted(filed_carriers & present)
            for key, selected, source in source_components[carrier]
        )
        total = tep_total(dataset, factors, current_year)
        totals: list[FiledCheck] = []
        pre_total = filed_values.get(f"tep.total.{current_year}")
        if pre_total is not None and isinstance(pre_total.value, int | float):
            totals.append(
                compare_filed(
                    f"tep.internal_total.{current_year}",
                    pre_total,
                    total,
                    locations,
                    "prelucrare_filed",
                )
            )
        if current_year == year and filed is not None and isinstance(filed.value, int | float):
            totals.append(compare_filed("annual.total_tep", filed, total, locations, "anexa"))
        yearly.append(
            YearCheck(
                current_year,
                tuple(sorted(filed_carriers - present)),
                tuple(sorted(present - filed_carriers)),
                components,
                tuple(totals),
            )
        )
    current = next((item for item in yearly if item.year == year), None)
    if current is None:
        return AnnualCheck("missing_inputs", filed, None, years=tuple(yearly))
    annex_total = next((item for item in current.totals if item.key == "annual.total_tep"), None)
    checks = (*current.components, *current.totals)
    if current.missing_carriers:
        status = "incomplete"
    elif any(item.status == "conflict" for item in checks):
        status = "conflict"
    elif any(item.status == "missing_inputs" for item in checks):
        status = "missing_inputs"
    elif annex_total is None:
        status = "missing"
    else:
        status = "match"
    return AnnualCheck(
        status,
        filed,
        annex_total.result if annex_total else None,
        annex_total.unknown_precision if annex_total else (),
        tuple(carrier.value for carrier in current.missing_carriers),
        tuple(carrier.value for carrier in current.unfiled_carriers),
        tuple(yearly),
    )


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
