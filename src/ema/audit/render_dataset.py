"""The parsed, sourced audit dataset with the auditor's review decisions laid over it."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from ema.core.review.fields import decided
from ema.core.review.models import Field
from ema.energy_data.carriers import Carrier, counts_in_total
from ema.energy_data.model import CarrierSeries, EnergyDataset, FiledValue, Reading

# Where a carrier's yearly spend sits among the Necesar's economic rows; the others have none.
COST_KEYS: dict[Carrier, str] = {
    Carrier.electricity_grid: "electricity_costs_lei",
    Carrier.purchased_heat: "heat_costs_lei",
    Carrier.natural_gas: "gas_costs_lei",
    Carrier.diesel: "diesel_costs_lei",
    Carrier.petrol: "petrol_costs_lei",
    Carrier.lpg: "lpg_costs_lei",
}


def _value(field: Field) -> tuple[bool, Any]:
    if field.review == "rejected":
        return True, None
    if decided(field):
        return True, field.value
    return False, None


def _period(parts: list[str]) -> tuple[int, int | None] | None:
    if not parts[0].isdecimal():
        return None
    if len(parts) == 1:
        return int(parts[0]), None
    if len(parts) == 2 and parts[1].isdecimal() and 1 <= int(parts[1]) <= 12:
        return int(parts[0]), int(parts[1])
    return None


def _reading(old: Reading | None, unit: str | None, value: Any) -> Reading | None:
    unit = old.unit if old is not None else unit
    if unit is None:
        return None
    return Reading(float(value) if value is not None else None, unit)


def _series(
    table: dict[int, CarrierSeries], year: int, month: int | None, unit: str | None, value: Any
) -> bool:
    series = table.get(year, CarrierSeries())
    old = series.months.get(month) if month is not None else series.annual
    reading = _reading(old, unit, value)
    if reading is None or reading == old:
        return False
    table[year] = (
        replace(series, annual=reading)
        if month is None
        else replace(series, months={**series.months, month: reading})
    )
    return True


def carrier_cost(by_key: Mapping[str, Field], carrier: Carrier, year: int) -> Field | None:
    """The carrier's positive, unrejected spend for the year: proof that the fuel was used."""
    name = COST_KEYS.get(carrier)
    field = by_key.get(f"audit.economics.{name}.{year}") if name else None
    if field is None or field.review == "rejected" or field.value is None:
        return None
    return field if float(field.value) > 0 else None


def _readings(series: CarrierSeries) -> list[Reading]:
    return [*series.months.values(), *([series.annual] if series.annual else [])]


def quantity_empty(series: CarrierSeries) -> bool:
    """No positive quantity anywhere in the year: absent, or the sum of empty cells."""
    return all(not reading.value for reading in _readings(series))


def _marked_unused(by_key: Mapping[str, Field], carrier: Carrier, year: int) -> bool:
    prefix = f"carrier.{carrier.value}.{year}"
    annual = by_key.get(prefix)
    months = [field for key, field in by_key.items() if key.startswith(f"{prefix}.")]
    return (annual is not None and annual.review == "rejected") or (
        bool(months) and all(field.review == "rejected" for field in months)
    )


class _Overlay:
    def __init__(self, dataset: EnergyDataset, fields: Iterable[Field]) -> None:
        self.dataset = dataset
        self.carriers = {carrier: dict(years) for carrier, years in dataset.carriers.items()}
        self.production = {name: dict(years) for name, years in dataset.production.items()}
        self.money = {
            "turnover": dict(dataset.turnover_lei),
            "energy_costs": dict(dataset.energy_costs_lei),
        }
        self.indicators = {key: dict(years) for key, years in dataset.filed_indicators.items()}
        self.by_key = {field.key: field for field in fields}
        self.changed: set[tuple[Carrier, int]] = set()
        self.filed: list[tuple[Carrier, int, Field, Any]] = []

    def apply(self, field: Field, value: Any) -> None:
        head, *rest = field.key.split(".")
        if head in self.money and len(rest) == 1 and rest[0].isdecimal():
            table = self.money[head]
            reading = _reading(table.get(int(rest[0])), field.unit, value)
            if reading is not None:
                table[int(rest[0])] = reading
            return
        if len(rest) < 2 or (period := _period(rest[1:])) is None:
            return
        year, month = period
        if head == "production" and rest[0] in self.production:
            unit = self.dataset.production_unit.get(rest[0], field.unit)
            _series(self.production[rest[0]], year, month, unit, value)
            return
        carrier = Carrier._value2member_map_.get(rest[0])
        if not isinstance(carrier, Carrier):
            return
        if head == "carrier_tep" and month is None:
            self.filed.append((carrier, year, field, value))
        elif head == "carrier":
            table = self.carriers.setdefault(carrier, {})
            if _series(table, year, month, field.unit, value):
                self.changed.add((carrier, year))

    def settle_use(self) -> None:
        """A carrier with no quantity in a year is dropped, unless its spend proves it was used."""
        for carrier, years in list(self.carriers.items()):
            if not counts_in_total(carrier):
                continue
            for year, series in list(years.items()):
                if _marked_unused(self.by_key, carrier, year):
                    del years[year]
                    self.changed.add((carrier, year))
                elif not quantity_empty(series):
                    continue
                elif carrier_cost(self.by_key, carrier, year) is None:
                    del years[year]
                else:
                    if readings := _readings(series):
                        years[year] = CarrierSeries(annual=Reading(None, readings[0].unit))
                    self.changed.add((carrier, year))
            if not years:
                del self.carriers[carrier]

    def settle_filed(self) -> None:
        for carrier, year in self.changed:
            self.indicators.get("tep_total", {}).pop(year, None)
            tep_field = self.by_key.get(f"carrier_tep.{carrier.value}.{year}")
            if tep_field is None or not _value(tep_field)[0]:
                self.indicators.get(f"tep.{carrier.value}", {}).pop(year, None)
        for carrier, year, field, value in self.filed:
            name = f"tep.{carrier.value}"
            previous = self.indicators.get(name, {}).get(year)
            if value is None:
                self.indicators.get(name, {}).pop(year, None)
            else:
                self.indicators.setdefault(name, {})[year] = FiledValue(
                    float(value), "tep", 2, source=f"review:{field.key}"
                )
            if (previous.value if previous else None) != (
                float(value) if value is not None else None
            ):
                self.indicators.get("tep_total", {}).pop(year, None)


def reviewed_dataset(dataset: EnergyDataset, fields: Iterable[Field]) -> EnergyDataset:
    """Decided values replace parsed ones; a rejected value is absent; the rest is untouched.

    A counted carrier with no quantity in a year has no series that year, so ch. 4 and the content
    checks agree; with a positive spend for that year its quantity stays missing instead. The
    auditor's rejection of the year marks the fuel as not used.

    A changed carrier value drops the filed tep of that year so ch. 4 recomputes it instead of
    printing a stale total; untouched filed values keep their cell source.
    """
    overlay = _Overlay(dataset, fields)
    for field in overlay.by_key.values():
        counts, value = _value(field)
        if counts:
            overlay.apply(field, value)
    overlay.settle_use()
    overlay.settle_filed()
    return replace(
        dataset,
        carriers=overlay.carriers,
        production=overlay.production,
        turnover_lei=overlay.money["turnover"],
        energy_costs_lei=overlay.money["energy_costs"],
        filed_indicators=overlay.indicators,
    )
