"""Pure calculations over source-unit energy readings."""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from ema.energy_data.carriers import WATER_CARRIERS, Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import (
    CarrierSeries,
    Derived,
    EnergyDataset,
    Indicators,
    Kind,
    field_key,
)


def annual(series: CarrierSeries, kind: Kind, name: str, year: int) -> Derived:
    """Use a filed annual reading, or require all twelve months before summing."""
    key = field_key(kind, name, year)
    if series.annual is not None:
        return Derived(
            series.annual.value,
            series.annual.unit,
            "annual.filed",
            (key,),
            missing=(key,) if series.annual.value is None else (),
            year=year,
        )
    if not series.months:
        return Derived(None, "", "annual.no_data", (), missing=(key,), year=year)
    unit = next(iter(series.months.values())).unit
    if any(reading.unit != unit for reading in series.months.values()):
        raise ValueError(f"mixed units in {key}")
    inputs = tuple(field_key(kind, name, year, month) for month in range(1, 13))
    missing = tuple(
        input_key
        for month, input_key in enumerate(inputs, 1)
        if month not in series.months or series.months[month].value is None
    )
    if missing:
        return Derived(None, unit, "annual.sum", inputs, missing=missing, year=year)
    return Derived(
        sum(series.months[month].value or 0.0 for month in range(1, 13)),
        unit,
        "annual.sum",
        inputs,
        year=year,
    )


def _reading(ds: EnergyDataset, carrier: Carrier, year: int, month: int | None) -> Derived:
    key = field_key("carrier", carrier.value, year, month)
    if carrier not in ds.carriers or year not in ds.carriers[carrier]:
        return Derived(None, "", "absent_carrier", (), missing=(), year=year)
    series = ds.carriers[carrier][year]
    if month is None:
        return annual(series, "carrier", carrier.value, year)
    reading = series.months.get(month)
    missing = (key,) if reading is None or reading.value is None else ()
    return Derived(
        reading.value if reading else None,
        reading.unit if reading else "",
        "reading.month",
        (key,),
        missing=missing,
        year=year,
    )


def _converted(
    ds: EnergyDataset,
    factors: FactorTable,
    carrier: Carrier,
    year: int,
    month: int | None,
    target: str,
) -> Derived:
    if carrier in WATER_CARRIERS:
        return Derived(None, target, "not_energy", factor_version=factors.version, year=year)
    reading = _reading(ds, carrier, year, month)
    if reading.formula_id == "absent_carrier":
        return Derived(
            None,
            target,
            "absent_carrier",
            factor_version=factors.version,
            missing=(field_key("carrier", carrier.value, year, month),),
            year=year,
        )
    if reading.value is None:
        return Derived(
            None,
            target,
            f"{target}.carrier",
            reading.inputs,
            factors.version,
            reading.missing,
            year=year,
        )
    factor = (
        factors.tep_factor(carrier, reading.unit, year)
        if target == "tep"
        else factors.co2_factor(carrier, reading.unit, year)
    )
    if factor is None:
        factor_kind = "tep" if target == "tep" else "co2"
        missing = f"factor.{factor_kind}.{carrier.value}.{reading.unit}.{year}"
        return Derived(
            None,
            target,
            f"{target}.carrier",
            reading.inputs,
            factors.version,
            (missing,),
            year=year,
        )
    weights = (factor.per_unit,) * len(reading.inputs)
    return Derived(
        reading.value * factor.per_unit,
        target,
        f"{target}.carrier",
        reading.inputs,
        factors.version,
        input_weights=weights,
        year=year,
    )


def tep(
    ds: EnergyDataset, factors: FactorTable, carrier: Carrier, year: int, month: int | None = None
) -> Derived:
    return _converted(ds, factors, carrier, year, month, "tep")


def co2(
    ds: EnergyDataset,
    factors: FactorTable,
    year: int,
    carrier: Carrier | None = None,
    month: int | None = None,
) -> Derived:
    if carrier is not None:
        return _converted(ds, factors, carrier, year, month, "t CO₂")
    return _total(ds, factors, year, month, "t CO₂")


def _total(
    ds: EnergyDataset, factors: FactorTable, year: int, month: int | None, target: str
) -> Derived:
    converted = [
        _converted(ds, factors, carrier, year, month, target)
        for carrier in ds.carriers
        if carrier not in WATER_CARRIERS and year in ds.carriers[carrier]
    ]
    inputs = tuple(key for part in converted for key in part.inputs)
    weights = tuple(weight for part in converted for weight in part.input_weights)
    missing = tuple(key for part in converted for key in part.missing)
    if not converted:
        missing = (f"energy.{year}",)
    return Derived(
        sum(part.value for part in converted if part.value is not None) if not missing else None,
        target,
        f"{target}.total",
        inputs,
        factors.version,
        missing,
        weights,
        year,
    )


def tep_total(
    ds: EnergyDataset, factors: FactorTable, year: int, month: int | None = None
) -> Derived:
    return _total(ds, factors, year, month, "tep")


def shares(ds: EnergyDataset, factors: FactorTable, year: int) -> dict[Carrier, Derived]:
    total = tep_total(ds, factors, year)
    result: dict[Carrier, Derived] = {}
    for carrier in ds.carriers:
        if carrier in WATER_CARRIERS or year not in ds.carriers[carrier]:
            continue
        part = tep(ds, factors, carrier, year)
        missing = (*part.missing, *total.missing)
        if total.value == 0:
            missing = (*missing, "total.zero")
        result[carrier] = Derived(
            part.value / total.value * 100 if part.value is not None and total.value else None,
            "%",
            "share.carrier",
            tuple(dict.fromkeys((*part.inputs, *total.inputs))),
            factors.version,
            tuple(dict.fromkeys(missing)),
            year=year,
        )
    return result


def specific_consumption(
    ds: EnergyDataset, factors: FactorTable, year: int, carrier: Carrier | None, product: str
) -> Derived:
    energy = tep_total(ds, factors, year) if carrier is None else tep(ds, factors, carrier, year)
    key = field_key("production", product, year)
    series = ds.production.get(product, {}).get(year)
    output_unit = f"tep/{ds.production_unit.get(product, '')}"
    if series is None:
        return Derived(
            None,
            output_unit,
            "specific.total" if carrier is None else "specific.carrier",
            energy.inputs,
            factors.version,
            (*energy.missing, key),
            year=year,
        )
    production = annual(series, "production", product, year)
    missing = (*energy.missing, *production.missing)
    if energy.formula_id in {"absent_carrier", "not_energy"} and carrier is not None:
        missing = (*missing, f"energy.{energy.formula_id}.{carrier.value}")
    declared_unit = ds.production_unit.get(product)
    if production.unit != declared_unit:
        missing = (*missing, f"unit.{key}.{declared_unit or 'undeclared'}")
    if production.value == 0:
        missing = (*missing, "production.zero")
    return Derived(
        energy.value / production.value
        if energy.value is not None and production.value and production.unit == declared_unit
        else None,
        output_unit,
        "specific.total" if carrier is None else "specific.carrier",
        (*energy.inputs, *production.inputs),
        factors.version,
        tuple(dict.fromkeys(missing)),
        year=year,
    )


def energy_intensity(ds: EnergyDataset, factors: FactorTable, year: int) -> Derived:
    energy = tep_total(ds, factors, year)
    key = field_key("turnover", None, year)
    turnover = ds.turnover_lei.get(year)
    missing = list(energy.missing)
    if turnover is None or turnover.value is None:
        missing.append(key)
    elif turnover.unit != "lei":
        missing.append(f"unit.{key}.lei")
    elif turnover.value == 0:
        missing.append("turnover.zero")
    elif turnover.value / 1000 == 0:
        missing.append("result.non_finite")
    return Derived(
        energy.value / (turnover.value / 1000)
        if energy.value is not None
        and turnover is not None
        and turnover.value
        and turnover.value / 1000
        and turnover.unit == "lei"
        else None,
        "tep/1000 lei",
        "intensity.energy",
        (*energy.inputs, key),
        factors.version,
        tuple(dict.fromkeys(missing)),
        year=year,
    )


def change(prev: Derived, cur: Derived) -> Derived:
    if prev.unit != cur.unit:
        raise ValueError("change needs matching units")
    missing = (*prev.missing, *cur.missing)
    if prev.value is None:
        missing = (*missing, "previous.missing")
    elif prev.value == 0:
        missing = (*missing, "previous.zero")
    if cur.value is None:
        missing = (*missing, "current.missing")
    if prev.year is None or cur.year is None or prev.year != cur.year - 1:
        missing = (*missing, "year.not_consecutive")
    return Derived(
        (cur.value - prev.value) / abs(prev.value) * 100
        if cur.value is not None
        and prev.value
        and cur.year is not None
        and prev.year == cur.year - 1
        else None,
        "%",
        "change.year",
        (*prev.inputs, *cur.inputs),
        cur.factor_version,
        tuple(dict.fromkeys(missing)),
        year=cur.year,
    )


def trend(values: Sequence[float], decimals: int = 2) -> str:
    """Classify the visible, rounded series by its least-squares slope."""
    if len(values) < 2:
        raise ValueError("trend needs at least two values")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("trend needs finite values")
    if decimals < 0:
        raise ValueError("trend decimals must be nonnegative")
    quantum = Decimal(1).scaleb(-decimals)
    visible = [Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP) for value in values]
    length = len(visible)
    numerator = sum(
        (Decimal(2 * index - length + 1) * value for index, value in enumerate(visible)),
        Decimal(0),
    )
    if numerator == 0:
        return "constantă"
    if numerator > 0:
        return "creștere"
    return "scădere"


def indicators(ds: EnergyDataset, factors: FactorTable) -> Indicators:
    carrier_tep = {
        year: {
            carrier: tep(ds, factors, carrier, year)
            for carrier in ds.carriers
            if carrier not in WATER_CARRIERS and year in ds.carriers[carrier]
        }
        for year in ds.years
    }
    totals = {year: tep_total(ds, factors, year) for year in ds.years}
    specific = {
        year: {
            product: {
                carrier: specific_consumption(ds, factors, year, carrier, product)
                for carrier in (None, *carrier_tep[year])
            }
            for product in ds.production
        }
        for year in ds.years
    }
    emissions = {
        year: {carrier: co2(ds, factors, year, carrier) for carrier in (None, *carrier_tep[year])}
        for year in ds.years
    }
    changes = {
        year: change(totals[previous], totals[year])
        for previous, year in zip(ds.years, ds.years[1:], strict=False)
    }
    total_values = [totals[year].value for year in ds.years]
    direction = (
        trend([value for value in total_values if value is not None])
        if len(total_values) >= 2 and all(value is not None for value in total_values)
        else None
    )
    return Indicators(
        carrier_tep,
        totals,
        {y: shares(ds, factors, y) for y in ds.years},
        specific,
        {y: energy_intensity(ds, factors, y) for y in ds.years},
        emissions,
        changes,
        direction,
    )
