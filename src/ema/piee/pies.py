"""Sourced photovoltaic and energy-mix shares for native PIEE 3D pies."""

from __future__ import annotations

from pathlib import Path

from ema.core.office.anchors import AnchorLedger
from ema.core.office.package import read_parts, write_parts
from ema.core.office.pie_replace import remove_pie_picture, replace_pie_picture
from ema.core.office.pie_xml import PieKind
from ema.energy_data.calc import annual, tep
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier, counts_in_total
from ema.piee.dataset import PieeData

PV_LABELS = (
    "Energia electrică achiziționată din SEN",
    "Energia electrică consumată din sistemul fotovoltaic propriu",
)
MIX_LABELS = ("Gaz", "Energie electrică totală", "Carburant")
EXPANDED_LABELS = (
    (Carrier.natural_gas, "Gaz"),
    (Carrier.electricity_grid, "Energie electrică"),
    (Carrier.sunflower_husks, "Coji de floarea-soarelui"),
    (Carrier.electricity_pv, "Energie electrică fotovoltaică"),
)
PIE_SLOTS: tuple[tuple[str, PieKind, int], ...] = (
    ("pie_rId21", "pv", -2),
    ("pie_rId22", "pv", -1),
    ("pie_rId23", "pv", 0),
    ("pie_rId36", "mix", -2),
    ("pie_rId37", "mix", -1),
    ("pie_rId38", "mix", 0),
)


def _annual(data: PieeData, carrier: Carrier, year: int) -> float | None:
    series = data.dataset.carriers.get(carrier, {}).get(year)
    if series is None:
        return None
    result = annual(series, "carrier", carrier.value, year)
    return result.value


def _tep(data: PieeData, carrier: Carrier, year: int) -> float | None:
    if data.prelucrare is not None:
        filed = data.prelucrare.filed.get(f"tep.{carrier.value}.{year}")
        if filed is not None and isinstance(filed.value, int | float):
            return float(filed.value)
    return tep(data.dataset, data.factors, carrier, year).value


def _shares(values: tuple[float | None, ...]) -> tuple[float, ...] | None:
    if any(item is None for item in values):
        return None
    present = tuple(float(item) for item in values if item is not None)
    total = sum(present)
    return tuple(item / total for item in present) if total > 0 else None


def _pv(data: PieeData, year: int) -> tuple[float, ...] | None:
    if not data.layout.separate_pv_figures:
        return None
    values = (
        _annual(data, Carrier.electricity_grid, year),
        _annual(data, Carrier.electricity_pv, year),
    )
    if data.pie_representation == "normalized":
        return _shares(values)
    return (
        tuple(item for item in values if item is not None)
        if all(item is not None for item in values)
        else None
    )


def _mix(data: PieeData, year: int) -> tuple[float, ...] | None:
    gas = _tep(data, Carrier.natural_gas, year)
    electricity = [
        _tep(data, carrier, year)
        for carrier in (Carrier.electricity_grid, Carrier.electricity_pv)
        if year in data.dataset.carriers.get(carrier, {})
    ]
    fuels = [
        _tep(data, carrier, year)
        for carrier in (Carrier.diesel, Carrier.petrol, Carrier.lpg)
        if year in data.dataset.carriers.get(carrier, {})
    ]
    if (
        gas is None
        or not electricity
        or not fuels
        or any(item is None for item in (*electricity, *fuels))
    ):
        return None
    return _shares(
        (
            gas,
            sum(item for item in electricity if item is not None),
            sum(item for item in fuels if item is not None),
        )
    )


def expanded_mix(data: PieeData, year: int) -> tuple[tuple[str, ...], tuple[float, ...]] | None:
    """Keep separately filed carriers when the prior PIEE presents raw values."""
    if Carrier.coke in data.dataset.carriers:
        order = (
            Carrier.natural_gas,
            Carrier.electricity_grid,
            Carrier.diesel,
            Carrier.coke,
            Carrier.lpg,
            Carrier.petrol,
            Carrier.electricity_pv,
            Carrier.sunflower_husks,
            Carrier.wood,
            Carrier.biomass,
            Carrier.purchased_heat,
        )
        names = {
            Carrier.natural_gas: " Gaz natural",
            Carrier.electricity_grid: "Energie electrica",
            Carrier.diesel: "Motorina",
            Carrier.coke: "Cocs",
            Carrier.lpg: "GPL",
        }
        labels: list[str] = []
        values: list[float] = []
        for carrier in order:
            if not counts_in_total(carrier) or year not in data.dataset.carriers.get(carrier, {}):
                continue
            amount = _tep(data, carrier, year)
            if amount is None:
                return None
            labels.append(names.get(carrier, CARRIER_NAMES_RO[carrier]))
            values.append(amount)
        return (tuple(labels), tuple(values)) if values else None
    gas = _tep(data, Carrier.natural_gas, year)
    grid = _tep(data, Carrier.electricity_grid, year)
    fuels = tuple(
        _tep(data, carrier, year)
        for carrier in (Carrier.diesel, Carrier.petrol, Carrier.lpg)
        if year in data.dataset.carriers.get(carrier, {})
    )
    if gas is None or grid is None or not fuels or any(item is None for item in fuels):
        return None
    labels = [EXPANDED_LABELS[0][1], EXPANDED_LABELS[1][1], "Carburant"]
    values = [gas, grid, sum(item for item in fuels if item is not None)]
    for carrier, label in EXPANDED_LABELS[2:]:
        if year not in data.dataset.carriers.get(carrier, {}):
            continue
        amount = _tep(data, carrier, year)
        if amount is None:
            return None
        labels.append(label)
        values.append(amount)
    return tuple(labels), tuple(values)


def render_pies(source: Path, data: PieeData, output: Path, ledger: AnchorLedger) -> None:
    parts = read_parts(source)
    for slot, kind, offset in PIE_SLOTS:
        year = data.year + offset
        if kind == "mix" and (
            data.pie_representation_source == "previous_piee"
            or Carrier.coke in data.dataset.carriers
        ):
            expanded = expanded_mix(data, year)
            labels = expanded[0] if expanded is not None else ()
            values = expanded[1] if expanded is not None else None
        else:
            labels = PV_LABELS if kind == "pv" else MIX_LABELS
            values = _pv(data, year) if kind == "pv" else _mix(data, year)
        if values is None:
            remove_pie_picture(parts, slot)
            ledger.record(slot, removed=True)
        else:
            replace_pie_picture(
                parts,
                slot,
                kind,
                labels,
                values,
                representation=data.pie_representation,
            )
            ledger.record(slot)
    write_parts(parts, output)
