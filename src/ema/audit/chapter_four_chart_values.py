"""Scaled, source-backed series and the nonzero chart data gate."""

from dataclasses import replace

from ema.audit.chapter_four_chart_text import readable_unit, scaled_unit
from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.chart_series import Series
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset


def display_unit(
    dataset: EnergyDataset,
    factors: FactorTable,
    metrics: tuple[Metric, ...],
    unit: str,
    years: tuple[int, ...],
) -> tuple[str, float]:
    """The unit and scale every printed value of these metrics shares, whatever the year."""
    shown, scale = scaled_unit(unit, metrics[0].kind)
    if metrics[0].kind != "specific":
        return shown, scale
    numbers = (
        value(dataset, factors, metric, year, filed=False)[0]
        for metric in metrics
        for year in years
    )
    return readable_unit(shown, scale, numbers)


def chart_series(
    dataset: EnergyDataset,
    factors: FactorTable,
    metrics: tuple[tuple[str, Metric], ...],
    scale: float,
    categories: list[str],
    year: int | None,
) -> list[Series]:
    result = [
        Series(
            name,
            categories,
            [
                value(dataset, factors, replace(metric, month=month), year, filed=False)[0]
                for month in range(1, len(categories) + 1)
            ]
            if year is not None
            else [
                value(dataset, factors, metric, int(category), filed=False)[0]
                for category in categories
            ],
        )
        for name, metric in metrics
    ]
    return [
        replace(item, values=[p * scale if p is not None else None for p in item.values])
        for item in result
    ]


def has_chart_data(series: list[Series]) -> bool:
    return any(point is not None and point != 0 for item in series for point in item.values)
