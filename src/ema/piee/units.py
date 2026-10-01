"""Convert production readings to the unit used in a delivered programme."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from docx.oxml.ns import qn

from ema.core.office.chart_series import read_series
from ema.core.office.package import read_parts, xml
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading

SCALES = {"tone": 1.0, "mii tone": 1000.0, "kWh": 1.0, "MWh": 1000.0, "mii MWh": 1_000_000.0}
FAMILIES = {
    "tone": "mass",
    "mii tone": "mass",
    "kWh": "energy",
    "MWh": "energy",
    "mii MWh": "energy",
}
UNIT = re.compile(r"(?<!\w)(mii\s+tone|tone|mii\s+MWh|MWh|kWh)(?!\w)", re.I)


def display_unit(unit: str) -> str:
    return "mii MWh" if unit.startswith("mii MWh") else unit


@dataclass(frozen=True)
class Conversion:
    source_unit: str
    presentation_unit: str
    multiplier: float
    source: str


def _base_unit(unit: str) -> str:
    normalized = " ".join(unit.split()).casefold()
    for candidate in sorted(SCALES, key=len, reverse=True):
        if normalized.startswith(candidate.casefold()):
            return candidate
    raise ValueError(f"unsupported production unit: {unit}")


def convert(value: float, source_unit: str, target_unit: str) -> float:
    source, target = _base_unit(source_unit), _base_unit(target_unit)
    if FAMILIES[source] != FAMILIES[target]:
        raise ValueError(f"incompatible production units: {source_unit} -> {target_unit}")
    return value * SCALES[source] / SCALES[target]


def delivered_production_unit(path: Path) -> str:
    """Read the first production figure's unit; reject mixed scales."""
    parts = read_parts(path)
    chart_parts = sorted(
        (name for name in parts if re.fullmatch(r"word/charts/chart\d+\.xml", name)),
        key=lambda name: int(name.rsplit("chart", 1)[1].split(".")[0]),
    )
    if chart_parts:
        chart = xml(parts, chart_parts[0])
        chart_text = " ".join(node.text or "" for node in chart.iter() if node.tag.endswith("}t"))
        matches = {_base_unit(match.group()) for match in UNIT.finditer(chart_text)}
        if len(matches) != 1:
            raise ValueError("first production figure has no unambiguous unit")
        return matches.pop()
    root = xml(parts, "word/document.xml")
    paragraphs = (
        "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
        for paragraph in root.iter(qn("w:p"))
    )
    candidates: set[str] = set()
    for paragraph in paragraphs:
        for match in UNIT.finditer(paragraph):
            unit = _base_unit(match.group())
            context = paragraph.casefold()
            if unit in {"tone", "mii tone", "mii MWh"} or "produc" in context:
                candidates.add(unit)
    if len(candidates) != 1:
        raise ValueError("delivered PIEE has no unambiguous production unit")
    return candidates.pop()


def delivered_pie_representation(path: Path) -> str:
    """Use the prior programme's chart-cache representation for pie values."""
    parts = read_parts(path)
    for name in sorted(parts):
        if not re.fullmatch(r"word/charts/chart\d+\.xml", name):
            continue
        root = xml(parts, name)
        if not list(
            root.iter("{http://schemas.openxmlformats.org/drawingml/2006/chart}pie3DChart")
        ):
            continue
        series = read_series(path, name)
        if len(series) != 1 or not series[0].values:
            raise ValueError("delivered PIEE pie has no unique value series")
        values = series[0].values
        if any(value is None or value < 0 for value in values):
            raise ValueError("delivered PIEE pie has invalid values")
        total = sum(value for value in values if value is not None)
        return "normalized" if abs(total - 1) <= 1e-9 else "raw"
    raise ValueError("delivered PIEE has no native pie to determine value representation")


def delivered_separate_pv_figures(path: Path) -> bool:
    """Check whether the prior document has a standalone PV-share pie."""
    parts = read_parts(path)
    for name in parts:
        if not re.fullmatch(r"word/charts/chart\d+\.xml", name):
            continue
        root = xml(parts, name)
        if not list(
            root.iter("{http://schemas.openxmlformats.org/drawingml/2006/chart}pie3DChart")
        ):
            continue
        series = read_series(path, name)
        if len(series) != 1 or len(series[0].categories) != 2:
            continue
        labels = " ".join(series[0].categories).casefold()
        if "fotovolta" in labels or "solar" in labels:
            return True
    return False


def presentation_dataset(
    dataset: EnergyDataset, previous_piee: Path | None
) -> tuple[EnergyDataset, Conversion | None]:
    if not dataset.production or previous_piee is None:
        return dataset, None
    target = delivered_production_unit(previous_piee)
    source_units = set(dataset.production_unit.values())
    if len(source_units) != 1:
        raise ValueError("production has multiple source units")
    source = source_units.pop()
    multiplier = convert(1.0, source, target)
    conversion = Conversion(source, target, multiplier, "previous_piee")
    if multiplier == 1 and _base_unit(source) == target:
        return dataset, conversion
    production = {
        product: {
            year: CarrierSeries(
                {
                    month: Reading(convert(reading.value, source, target), target)
                    for month, reading in series.months.items()
                    if reading.value is not None
                },
                Reading(convert(series.annual.value, source, target), target)
                if series.annual is not None and series.annual.value is not None
                else None,
            )
            for year, series in years.items()
        }
        for product, years in dataset.production.items()
    }
    return (
        EnergyDataset(
            dataset.years,
            dataset.carriers,
            production,
            dict.fromkeys(dataset.production_unit, target),
            dataset.turnover_lei,
            dataset.energy_costs_lei,
            dataset.filed_indicators,
            dataset.energy_inventory_complete,
            dataset.production_name,
        ),
        conversion,
    )
