"""S7 analysis values bound to the reviewed approved PIEE chart bookmarks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.chart_series import Series
from ema.energy_data.calc import co2
from ema.energy_data.carriers import CARRIER_NAMES_RO, WATER_CARRIERS, Carrier
from ema.energy_data.model import EnergyDataset
from ema.piee.dataset import PieeData

MONTHS = (
    "Ianuarie",
    "Februarie",
    "Martie",
    "Aprilie",
    "Mai",
    "Iunie",
    "Iulie",
    "August",
    "Septembrie",
    "Octombrie",
    "Noiembrie",
    "Decembrie",
)
Kind = Literal[
    "production",
    "carrier",
    "fuel",
    "fuel_total",
    "water",
    "total_tep",
    "specific",
    "specific_fuel",
    "intensity",
    "energy_share",
    "co2",
]


@dataclass(frozen=True)
class ChartBinding:
    slot: str
    kind: Kind
    carrier: Carrier | None = None
    year_offset: int | None = None


BINDINGS: tuple[ChartBinding, ...] = (
    *(ChartBinding(f"chart_{i}", "production", year_offset=i - 3) for i in (1, 2, 3)),
    ChartBinding("chart_4", "production"),
    *(ChartBinding(f"chart_{i}", "carrier", Carrier.electricity_grid, i - 7) for i in (5, 6, 7)),
    ChartBinding("chart_8", "carrier", Carrier.electricity_grid),
    *(ChartBinding(f"chart_{i}", "carrier", Carrier.electricity_pv, i - 11) for i in (9, 10, 11)),
    ChartBinding("chart_12", "carrier", Carrier.electricity_pv),
    *(ChartBinding(f"chart_{i}", "carrier", Carrier.natural_gas, i - 15) for i in (13, 14, 15)),
    ChartBinding("chart_16", "carrier", Carrier.natural_gas),
    *(ChartBinding(f"chart_{i}", "fuel", year_offset=i - 19) for i in (17, 18, 19)),
    ChartBinding("chart_20", "fuel_total"),
    *(ChartBinding(f"chart_{i}", "water", Carrier.water_potable, i - 23) for i in (21, 22, 23)),
    ChartBinding("chart_24", "water", Carrier.water_potable),
    ChartBinding("chart_25", "specific", Carrier.electricity_grid),
    ChartBinding("chart_26", "specific", Carrier.natural_gas),
    ChartBinding("chart_27", "specific_fuel"),
    ChartBinding("chart_28", "specific"),
    ChartBinding("chart_29", "specific", Carrier.water_potable),
    ChartBinding("chart_30", "intensity"),
    ChartBinding("chart_31", "co2"),
)


def _years(data: PieeData) -> tuple[int, int, int]:
    return (data.year - 2, data.year - 1, data.year)


def _production(ds: EnergyDataset) -> tuple[str, str] | None:
    if not ds.production:
        return None
    product = next(iter(ds.production))
    unit = ds.production_unit.get(product, "")
    return product, "mii MWh" if unit.startswith("mii MWh") else unit


def _water(data: PieeData, carrier: Carrier, year: int, month: int | None) -> float | None:
    sourced = data.dataset.carriers.get(carrier, {}).get(year)
    if sourced is not None:
        reading = sourced.annual if month is None else sourced.months.get(month)
        return reading.value if reading is not None else None
    block = data.necesar.water.get(carrier)
    values = block.years.get(year) if block else None
    if values is None:
        return None
    if (
        values.total is not None
        and values.total.value == 0
        and all(item is None for item in values.months)
    ):
        return None
    found = values.total if month is None else values.months[month - 1]
    return (
        float(found.value) if found is not None and isinstance(found.value, int | float) else None
    )


def _filed(data: PieeData, kind: Kind, year: int) -> float | None:
    if data.prelucrare is None:
        return None
    prefix = {
        "total_tep": "tep.total",
        "co2": "co2.total",
        "intensity": "intensity",
        "energy_share": "energy_share",
    }.get(kind)
    found = data.prelucrare.filed.get(f"{prefix}.{year}") if prefix is not None else None
    return (
        float(found.value) if found is not None and isinstance(found.value, int | float) else None
    )


def _fuel_value(data: PieeData, kind: Kind, year: int) -> float | None:
    fuels = tuple(
        carrier
        for carrier in (Carrier.diesel, Carrier.petrol, Carrier.lpg)
        if year in data.dataset.carriers.get(carrier, {})
    )
    if not fuels:
        return None
    if kind == "fuel_total":
        return value(data.dataset, data.factors, Metric("carrier", fuels), year)[0]
    production = _production(data.dataset)
    if production is None:
        return None
    scale = 1000 if production[1] == "tone" else 1
    if data.production_conversion is not None and data.prelucrare is not None:
        output = value(
            data.dataset, data.factors, Metric("production", product=production[0]), year
        )[0]
        filed = [data.prelucrare.filed.get(f"tep.{carrier.value}.{year}") for carrier in fuels]
        if output and all(
            item is not None and isinstance(item.value, int | float) for item in filed
        ):
            return scale * (
                sum(
                    float(item.value)
                    for item in filed
                    if item is not None and isinstance(item.value, int | float)
                )
                / output
            )
    values = [
        value(data.dataset, data.factors, Metric("specific", (carrier,), production[0]), year)[0]
        for carrier in fuels
    ]
    return (
        scale * sum(item for item in values if item is not None)
        if all(item is not None for item in values)
        else None
    )


def _co2_total(data: PieeData, year: int) -> float | None:
    """PV is zero-emission in the approved PIEE; sum only emitting carriers."""
    carriers = tuple(
        carrier
        for carrier in data.dataset.carriers
        if carrier not in WATER_CARRIERS
        and carrier != Carrier.electricity_pv
        and year in data.dataset.carriers[carrier]
    )
    parts = [co2(data.dataset, data.factors, year, carrier).value for carrier in carriers]
    return (
        sum(item for item in parts if item is not None)
        if parts and all(item is not None for item in parts)
        else None
    )


def _metric(  # noqa: C901, PLR0911, PLR0912
    data: PieeData, binding: ChartBinding, year: int, month: int | None
) -> float | None:
    if binding.kind == "water":
        assert binding.carrier is not None
        return _water(data, binding.carrier, year, month)
    if binding.kind in {"fuel_total", "specific_fuel"}:
        return _fuel_value(data, binding.kind, year)
    filed = _filed(data, binding.kind, year)
    if filed is not None:
        return filed
    if binding.kind == "energy_share":
        return None
    if (
        binding.kind == "specific"
        and data.production_conversion is not None
        and data.prelucrare is not None
    ):
        key = binding.carrier.value if binding.carrier is not None else "total"
        chosen = data.prelucrare.filed.get(f"specific.{key}.{year}")
        if chosen is not None and isinstance(chosen.value, int | float):
            return float(chosen.value)
    production = _production(data.dataset)
    if binding.kind in {"production", "specific"} and production is None:
        return None
    if binding.kind == "production":
        assert production is not None
        metric = Metric("production", product=production[0], month=month)
    elif binding.kind == "carrier":
        assert binding.carrier is not None
        metric = Metric("carrier", (binding.carrier,), month=month)
    elif binding.kind == "total_tep":
        metric = Metric("tep_total")
    elif binding.kind == "specific":
        assert production is not None
        if binding.carrier in WATER_CARRIERS:
            assert binding.carrier is not None
            water = _water(data, binding.carrier, year, None)
            output = value(
                data.dataset, data.factors, Metric("production", product=production[0]), year
            )[0]
            return water / output if water is not None and output else None
        metric = Metric("specific", (binding.carrier,) if binding.carrier else (), production[0])
    elif binding.kind == "intensity":
        metric = Metric("intensity")
    elif binding.kind == "co2":
        return _co2_total(data, year)
    else:
        raise ValueError("fuel series must specify its carrier")
    result = value(data.dataset, data.factors, metric, year)[0]
    if (
        result is not None
        and binding.kind == "specific"
        and binding.carrier not in WATER_CARRIERS
        and production is not None
        and production[1] == "tone"
    ):
        return result * 1000
    return result


def _series_name(  # noqa: C901, PLR0911
    data: PieeData,
    binding: ChartBinding,
    carrier: Carrier | None,
    production: tuple[str, str] | None,
) -> str:
    if carrier is not None:
        return ""
    if binding.kind == "production" and production is not None:
        return (
            data.dataset.production_unit.get(production[0], "")
            if binding.year_offset is not None
            else production[1]
        )
    if binding.kind == "co2":
        return "Impact de mediu, t CO₂/an"
    if binding.kind == "fuel_total":
        return "total tone"
    unit = (
        "mii tone"
        if production is not None and production[1] == "tone"
        else (production[1] if production is not None else "")
    )
    if binding.kind == "specific_fuel" and production is not None:
        return f"consum specific anual de carburant, tep/{unit}"
    if binding.kind == "specific" and production is not None:
        if binding.carrier in WATER_CARRIERS:
            assert binding.carrier is not None
            return (
                f"consum specific anual de {CARRIER_NAMES_RO[binding.carrier]}, m3/{production[1]}"
            )
        if binding.carrier == Carrier.electricity_grid:
            subject = "de energie electrica"
        elif binding.carrier == Carrier.natural_gas:
            subject = "de gaz natural"
        elif binding.carrier is not None:
            subject = f"de {CARRIER_NAMES_RO[binding.carrier]}"
        else:
            subject = "total"
        return f"consum specific anual {subject}, tep/{unit}"
    return ""


def _series(data: PieeData, binding: ChartBinding, carrier: Carrier | None = None) -> Series | None:
    categories: list[str]
    if binding.year_offset is not None:
        year = data.year + binding.year_offset
        values = [
            _metric(
                data,
                ChartBinding(binding.slot, "carrier", carrier) if carrier else binding,
                year,
                month,
            )
            for month in range(1, 13)
        ]
        spaced = binding.kind == "production" or (
            binding.kind == "carrier"
            and binding.carrier in {Carrier.electricity_grid, Carrier.natural_gas}
        )
        categories = [f" {month} " if spaced else month for month in MONTHS]
    else:
        values = [
            _metric(
                data,
                ChartBinding(binding.slot, "carrier", carrier) if carrier else binding,
                year,
                None,
            )
            for year in _years(data)
        ]
        categories = [str(year) for year in _years(data)]
    if all(item is None for item in values):
        return None
    return Series(
        _series_name(data, binding, carrier, _production(data.dataset)), categories, values
    )


def chart_series(data: PieeData, binding: ChartBinding) -> tuple[Series | None, ...]:
    """Return None for an absent figure or absent fuel series; missing cells remain gaps."""
    if binding.carrier == Carrier.electricity_pv and not data.layout.separate_pv_figures:
        return (None,)
    if binding.kind == "fuel":
        return tuple(
            _series(data, binding, carrier)
            for carrier in (Carrier.diesel, Carrier.petrol, Carrier.lpg)
        )
    return (_series(data, binding),)
