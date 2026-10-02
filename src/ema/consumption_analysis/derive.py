"""Compute one metric value from the energy dataset, in its source units."""

from __future__ import annotations

from ema.consumption_analysis.metric_kind import Metric
from ema.energy_data.calc import (
    annual,
    co2,
    energy_intensity,
    specific_consumption,
    tep,
    tep_total,
    water_specific,
)
from ema.energy_data.carriers import Carrier
from ema.energy_data.co2_sum import co2_sum
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset, field_key


def production(ds: EnergyDataset, metric: Metric, year: int) -> tuple[float | None, str]:
    if metric.product is None:
        raise ValueError("production metric needs a product")
    series = ds.production.get(metric.product, {}).get(year)
    key = field_key("production", metric.product, year, metric.month)
    if series is None:
        return None, key
    if metric.month is None:
        return annual(series, "production", metric.product, year).value, key
    reading = series.months.get(metric.month)
    return (reading.value if reading else None), key


def _carrier_value(
    ds: EnergyDataset, carrier: Carrier, year: int, month: int | None
) -> tuple[float | None, str]:
    series = ds.carriers.get(carrier, {}).get(year)
    if series is None:
        return None, ""
    if month is None:
        result = annual(series, "carrier", carrier.value, year)
        return result.value, result.unit
    reading = series.months.get(month)
    return (reading.value, reading.unit) if reading else (None, "")


def carriers(ds: EnergyDataset, metric: Metric, year: int) -> tuple[float | None, str]:
    if not metric.carriers:
        raise ValueError("carrier metric needs at least one carrier")
    readings = [_carrier_value(ds, carrier, year, metric.month) for carrier in metric.carriers]
    keys = "+".join(
        field_key("carrier", carrier.value, year, metric.month) for carrier in metric.carriers
    )
    if any(number is None for number, _ in readings):
        return None, keys
    if len({unit for _, unit in readings}) != 1:
        raise ValueError("combined carrier readings have different units")
    return sum(number for number, _ in readings if number is not None), keys


def derived(  # noqa: C901, PLR0912
    ds: EnergyDataset, factors: FactorTable, metric: Metric, year: int, *, filed: bool = True
) -> tuple[float | None, str | None]:
    if metric.kind == "tep_total":
        result = tep_total(ds, factors, year, metric.month)
    elif metric.kind == "tep_monthly_sum":
        if len(metric.carriers) != 1 or metric.month is not None:
            raise ValueError("annual monthly tep metric needs one carrier and no month")
        parts = [tep(ds, factors, metric.carriers[0], year, month) for month in range(1, 13)]
        return (
            sum(part.value for part in parts if part.value is not None)
            if all(part.value is not None for part in parts)
            else None,
            "+".join(key for part in parts for key in part.inputs),
        )
    elif metric.kind == "intensity":
        result = energy_intensity(ds, factors, year, filed=filed)
    elif metric.kind == "specific":
        if metric.product is None:
            raise ValueError("specific metric needs a product")
        if len(metric.carriers) > 1:
            raise ValueError("specific metric accepts at most one carrier")
        result = specific_consumption(
            ds,
            factors,
            year,
            metric.carriers[0] if metric.carriers else None,
            metric.product,
            filed=filed,
        )
    elif metric.kind == "water_specific":
        if metric.product is None or len(metric.carriers) != 1:
            raise ValueError("water-specific metric needs a product and water carrier")
        result = water_specific(ds, year, metric.carriers[0], metric.product)
    elif metric.kind == "co2" and len(metric.carriers) > 1:
        result = co2_sum(ds, factors, year, metric.carriers)
    elif metric.kind in {"tep", "co2"}:
        if len(metric.carriers) != 1 and (metric.kind == "tep" or metric.carriers):
            raise ValueError(f"{metric.kind} metric needs one carrier or total CO2")
        carrier = metric.carriers[0] if metric.carriers else None
        if metric.kind == "tep":
            assert carrier is not None
            result = tep(ds, factors, carrier, year, metric.month)
        else:
            result = co2(ds, factors, year, carrier, metric.month)
    else:
        raise ValueError("derived metric kind is invalid")
    return result.value, "+".join(result.inputs) or result.formula_id
