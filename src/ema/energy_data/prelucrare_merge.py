"""Prelucrare source precedence with explicit conflicts."""

import math
import re

from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading
from ema.energy_data.prelucrare_types import PrelucrareData, SourceConflict


def annual_readings_match(left: Reading, right: Reading) -> bool:
    """Ignore a per-year unit suffix while preserving real value and unit conflicts."""
    left_unit = re.sub(r"\s*/\s*an\s*$", "", left.unit, flags=re.I).strip().casefold()
    right_unit = re.sub(r"\s*/\s*an\s*$", "", right.unit, flags=re.I).strip().casefold()
    if left_unit != right_unit:
        return False
    if left.value == right.value:
        return True
    return (
        left.value is not None
        and right.value is not None
        and math.isclose(left.value, right.value, rel_tol=1e-9, abs_tol=1e-9)
    )


def _series_conflicts(
    field: str, selected: CarrierSeries, previous: CarrierSeries | None
) -> list[SourceConflict]:
    if previous is None:
        return []
    result = [
        SourceConflict(f"{field}.{month:02d}", reading, old)
        for month, reading in selected.months.items()
        if (old := previous.months.get(month)) is not None and old != reading
    ]
    if (
        selected.annual is not None
        and previous.annual is not None
        and not annual_readings_match(selected.annual, previous.annual)
    ):
        result.append(SourceConflict(field, selected.annual, previous.annual))
    return result


def merge_prelucrare(
    other: EnergyDataset, imported: PrelucrareData
) -> tuple[EnergyDataset, list[SourceConflict]]:
    chosen = imported.dataset
    conflicts: list[SourceConflict] = []
    carriers = {carrier: dict(series) for carrier, series in other.carriers.items()}
    for carrier, years in chosen.carriers.items():
        target = carriers.setdefault(carrier, {})
        for year, pre_series in years.items():
            conflicts.extend(
                _series_conflicts(f"carrier.{carrier.value}.{year}", pre_series, target.get(year))
            )
            target[year] = pre_series
    production = {key: dict(values) for key, values in other.production.items()}
    units = dict(other.production_unit)
    if (
        len(production) == len(chosen.production) == 1
        and next(iter(units.values())) == "kWh"
        and next(iter(chosen.production_unit.values())) == "mii MWh gaz vehiculat"
    ):
        source_key = next(iter(production))
        target_key = next(iter(chosen.production))
        converted = {}
        for year, series in production.pop(source_key).items():
            months = {
                month: Reading(
                    reading.value / 1_000_000 if reading.value is not None else None,
                    "mii MWh gaz vehiculat",
                )
                for month, reading in series.months.items()
            }
            annual = (
                Reading(
                    series.annual.value / 1_000_000 if series.annual.value is not None else None,
                    "mii MWh gaz vehiculat",
                )
                if series.annual is not None
                else None
            )
            converted[year] = CarrierSeries(months, annual)
        production[target_key] = converted
        units = {target_key: "mii MWh gaz vehiculat"}
    for key, values in chosen.production.items():
        target = production.setdefault(key, {})
        for year, pre_series in values.items():
            conflicts.extend(
                _series_conflicts(f"production.{key}.{year}", pre_series, target.get(year))
            )
            target[year] = pre_series
    turnover = {**other.turnover_lei, **chosen.turnover_lei}
    costs = {**other.energy_costs_lei, **chosen.energy_costs_lei}
    for kind, selected, previous in (
        ("turnover", chosen.turnover_lei, other.turnover_lei),
        ("energy_costs", chosen.energy_costs_lei, other.energy_costs_lei),
    ):
        for year, reading in selected.items():
            if (old := previous.get(year)) is not None and old != reading:
                conflicts.append(SourceConflict(f"{kind}.{year}", reading, old))
    years = tuple(sorted(set(other.years) | set(chosen.years)))
    return EnergyDataset(
        years,
        carriers,
        production,
        {**units, **chosen.production_unit},
        turnover,
        costs,
        production_name={**chosen.production_name, **other.production_name},
    ), conflicts
