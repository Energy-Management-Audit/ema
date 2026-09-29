"""Scaled, source-backed series and the nonzero chart data gate."""

from dataclasses import replace

from ema.audit.chapter_four_chart_text import scaled_unit
from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.chart_series import Series
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset


def chart_series(
    dataset: EnergyDataset,
    factors: FactorTable,
    metrics: tuple[tuple[str, Metric], ...],
    unit: str,
    categories: list[str],
    year: int | None,
) -> list[Series]:
    result = [
        Series(
            name,
            categories,
            [
                value(dataset, factors, replace(metric, month=month), year)[0]
                for month in range(1, len(categories) + 1)
            ]
            if year is not None
            else [value(dataset, factors, metric, int(category))[0] for category in categories],
        )
        for name, metric in metrics
    ]
    return [
        replace(item, values=[p * scale if p is not None else None for p in item.values])
        for item, (_, metric) in zip(result, metrics, strict=True)
        for _, scale in [scaled_unit(unit, metric.kind)]
    ]


def has_chart_data(series: list[Series]) -> bool:
    return any(point is not None and point != 0 for item in series for point in item.values)
