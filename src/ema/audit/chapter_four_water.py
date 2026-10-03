"""Chapter four leaves out a water carrier the client has no reading for."""

from __future__ import annotations

from dataclasses import replace

from ema.energy_data.carriers import WATER_CARRIERS, Carrier
from ema.energy_data.model import EnergyDataset


def has_readings(dataset: EnergyDataset, carrier: Carrier) -> bool:
    return any(
        (series.annual is not None and series.annual.value is not None)
        or any(reading.value is not None for reading in series.months.values())
        for series in dataset.carriers.get(carrier, {}).values()
    )


def without_empty_water(dataset: EnergyDataset) -> EnergyDataset:
    """A water carrier the client reports no value for gets no block, as in PIEE."""
    carriers = {
        carrier: series
        for carrier, series in dataset.carriers.items()
        if carrier not in WATER_CARRIERS or has_readings(dataset, carrier)
    }
    return replace(dataset, carriers=carriers)
