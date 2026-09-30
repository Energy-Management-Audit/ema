"""Hold new reader fields at the PIEE boundary until reconciliation consumes them."""

from __future__ import annotations

from ema.energy_data.carriers import Carrier
from ema.energy_data.model import CarrierSeries, EnergyDataset
from ema.energy_data.prelucrare_types import PrelucrareData
from ema.energy_data.source import normal


def existing_piee_readings(imported: PrelucrareData) -> PrelucrareData:  # noqa: C901, PLR0912
    """Keep the pre-expansion readings used by the existing PIEE workflow."""
    located = dict(imported.located)
    carriers: dict[Carrier, dict[int, CarrierSeries]] = {}
    for carrier, by_year in imported.dataset.carriers.items():
        for year, series in by_year.items():
            key = f"carrier.{carrier.value}.{year}"
            if (carrier, year) in imported.deferred_series:
                for field in tuple(located):
                    if field == key or field.startswith(f"{key}."):
                        located.pop(field)
                continue
            annual_source = located.get(key)
            water_block = (
                annual_source is not None and normal(annual_source.ref.sheet) == "consum apa"
            )
            annual = None if water_block else imported.previous_annual.get(key)
            if annual is None:
                located.pop(key, None)
            else:
                located[key] = imported.previous_annual_located[key]
            carriers.setdefault(carrier, {})[year] = CarrierSeries(series.months, annual)

    production: dict[str, dict[int, CarrierSeries]] = {}
    for name, by_year in imported.dataset.production.items():
        for year, series in by_year.items():
            key = f"production.{name}.{year}"
            if year in imported.deferred_production:
                for field in tuple(located):
                    if field == key or field.startswith(f"{key}."):
                        located.pop(field)
                continue
            annual = (
                None
                if imported.dataset.production_unit.get(name, "").startswith("mii ")
                else series.annual
            )
            if annual is None:
                located.pop(key, None)
            production.setdefault(name, {})[year] = CarrierSeries(series.months, annual)

    source = imported.dataset
    dataset = EnergyDataset(
        source.years,
        carriers,
        production,
        {name: unit for name, unit in source.production_unit.items() if name in production},
        source.turnover_lei,
        source.energy_costs_lei,
        source.filed_indicators,
        source.energy_inventory_complete,
        source.production_name,
    )
    return PrelucrareData(dataset, imported.factors, located, imported.filed, imported.issues)
