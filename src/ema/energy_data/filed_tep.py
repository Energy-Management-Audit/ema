"""The client's filed tep as a stand-in energy value; only PIEE prints it."""

from __future__ import annotations

from ema.energy_data.carriers import Carrier, counts_in_total
from ema.energy_data.model import Derived, EnergyDataset, field_key


def filed_tep(ds: EnergyDataset, carrier: Carrier | None, year: int) -> Derived | None:
    """The filed total (carrier None) or one carrier's filed tep, keyed like its source cells."""
    filed = ds.filed_indicators.get("tep_total" if carrier is None else f"tep.{carrier.value}", {})
    value = filed.get(year)
    if value is None:
        return None
    names = (
        tuple(name for name in ds.carriers if counts_in_total(name) and year in ds.carriers[name])
        if carrier is None
        else (carrier,)
    )
    inputs = tuple(field_key("carrier_tep", name.value, year) for name in names)
    return Derived(value.value, "tep", "filed.tep", inputs, "filed", year=year)
