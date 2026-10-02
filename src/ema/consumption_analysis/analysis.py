"""Deterministic chapter-four values placed in authored document prototypes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ema.consumption_analysis.derive import carriers, derived, production
from ema.consumption_analysis.metric_kind import Metric
from ema.consumption_analysis.phrases import phrase_bank, trend_direction, trend_phrase
from ema.core.office.blocks import Block, NativeChart, Num, Paragraph, Segment, Table
from ema.core.office.chart_series import Series
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset, FiledValue


@dataclass(frozen=True)
class TablePlan:
    proto: str
    columns: tuple[Metric, ...]
    years: tuple[int, ...]
    decimals: int = 2
    grouping: bool = False
    header_rows: int = 1


@dataclass(frozen=True)
class MatrixTablePlan:
    proto: str
    rows: tuple[tuple[str, tuple[Metric, ...]], ...]
    years: tuple[int, ...]
    decimals: int = 2
    header_rows: int = 1


@dataclass(frozen=True)
class ChartPlan:
    proto: str
    part: str
    name: str
    metric: Metric
    years: tuple[int, ...]
    categories: tuple[str, ...]
    decimals: int = 2
    title: str | None = None


@dataclass(frozen=True)
class TrendPlan:
    proto: str
    subject: str
    figure_number: str
    chart: ChartPlan
    year: int | None = None
    scope: Literal["audit", "piee"] = "audit"
    source_document: str | None = None
    source_paragraph: int | None = None


@dataclass(frozen=True)
class NumericSentencePlan:
    proto: str
    metric: Metric
    year: int
    source_document: str
    source_paragraph: int
    decimals: int = 4
    grouping: bool = False


type ItemPlan = TablePlan | MatrixTablePlan | ChartPlan | TrendPlan | NumericSentencePlan


@dataclass(frozen=True)
class SectionPlan:
    id: str
    stage: Literal[
        "production", "carrier", "equivalent", "conclusions", "specific", "intensity", "environment"
    ]
    items: tuple[ItemPlan, ...]


@dataclass(frozen=True)
class AnalysisSection:
    id: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class ResolvedValue:
    value: float | None
    fact: str | None
    origin: Literal["recomputed", "filed", "missing"]
    conflict: bool = False


def _filed_key(metric: Metric) -> str | None:
    if metric.month is not None:
        return None
    if metric.kind == "filed":
        return metric.product
    if metric.kind == "tep" and len(metric.carriers) == 1:
        return f"tep.{metric.carriers[0].value}"
    if metric.kind in {"intensity", "tep_total"}:
        return metric.kind
    if metric.kind == "co2" and len(metric.carriers) <= 1:
        return f"co2.{metric.carriers[0].value}" if metric.carriers else "co2.total"
    return None


def resolve_value(
    ds: EnergyDataset, factors: FactorTable, metric: Metric, year: int, *, filed: bool = True
) -> ResolvedValue:
    """Keep the filed alternative; prefer a complete calculation and flag a disagreement.

    With ``filed=False`` (the audit) a value that cannot be calculated stays missing: a filed
    figure never stands in for it, so a printed total always matches its printed components.
    """
    if year not in ds.years:
        raise ValueError("metric year is outside the dataset")
    key = _filed_key(metric)
    filed_value: FiledValue | None = ds.filed_indicators.get(key, {}).get(year) if key else None
    if metric.kind == "filed":
        return (
            ResolvedValue(filed_value.value, f"filed:{filed_value.source}", "filed")
            if filed_value
            else ResolvedValue(None, key, "missing")
        )
    if (
        filed
        and not ds.energy_inventory_complete
        and (
            metric.kind in {"tep_total", "intensity"}
            or (metric.kind == "co2" and not metric.carriers)
        )
    ):
        return (
            ResolvedValue(filed_value.value, f"filed:{filed_value.source}", "filed")
            if filed_value
            else ResolvedValue(None, key, "missing")
        )
    if metric.kind == "production":
        computed = production(ds, metric, year)
    elif metric.kind == "carrier":
        computed = carriers(ds, metric, year)
    else:
        computed = derived(ds, factors, metric, year, filed=filed)
    if computed[0] is None:
        return (
            ResolvedValue(filed_value.value, f"filed:{filed_value.source}", "filed")
            if filed and filed_value
            else ResolvedValue(None, computed[1], "missing")
        )
    conflict = bool(
        filed_value
        and abs(computed[0] - filed_value.value) > 0.5 * 10 ** (-filed_value.decimals) + 1e-12
    )
    return ResolvedValue(computed[0], computed[1], "recomputed", conflict)


def value(
    ds: EnergyDataset, factors: FactorTable, metric: Metric, year: int, *, filed: bool = True
) -> tuple[float | None, str | None]:
    resolved = resolve_value(ds, factors, metric, year, filed=filed)
    return resolved.value, resolved.fact


def _table(ds: EnergyDataset, factors: FactorTable, plan: TablePlan) -> Table:
    rows: list[list[list[Segment]]] = []
    for year in plan.years:
        cells: list[list[Segment]] = [[str(year)]]
        for metric in plan.columns:
            number, fact = value(ds, factors, metric, year)
            cells.append(
                [
                    Num(
                        number,
                        metric.decimals if metric.decimals is not None else plan.decimals,
                        fact=fact,
                        grouping=metric.grouping if metric.grouping is not None else plan.grouping,
                    )
                ]
            )
        rows.append(cells)
    return Table(plan.proto, rows, plan.header_rows)


def _matrix_table(ds: EnergyDataset, factors: FactorTable, plan: MatrixTablePlan) -> Table:
    rows: list[list[list[Segment]]] = []
    for label, metrics in plan.rows:
        if len(metrics) != len(plan.years):
            raise ValueError("matrix table columns must match years")
        cells: list[list[Segment]] = [[label]]
        for year, metric in zip(plan.years, metrics, strict=True):
            number, fact = value(ds, factors, metric, year)
            cells.append([Num(number, plan.decimals, fact=fact)])
        rows.append(cells)
    return Table(plan.proto, rows, plan.header_rows)


def _chart_values(ds: EnergyDataset, factors: FactorTable, plan: ChartPlan) -> list[float | None]:
    if plan.metric.month is not None:
        raise ValueError("chart metric month is supplied by its categories")
    if len(plan.years) == 1 and len(plan.categories) == 12:
        year = plan.years[0]
        return [
            value(
                ds,
                factors,
                Metric(plan.metric.kind, plan.metric.carriers, plan.metric.product, month),
                year,
            )[0]
            for month in range(1, 13)
        ]
    if len(plan.categories) != len(plan.years):
        raise ValueError("chart categories must match annual years or twelve months")
    return [value(ds, factors, plan.metric, year)[0] for year in plan.years]


def _chart(ds: EnergyDataset, factors: FactorTable, plan: ChartPlan) -> NativeChart:
    series = Series(plan.name, list(plan.categories), _chart_values(ds, factors, plan))
    return NativeChart(plan.proto, plan.part, [series], plan.title)


def _sentence(ds: EnergyDataset, factors: FactorTable, plan: TrendPlan) -> Paragraph | None:
    direction = trend_direction(_chart_values(ds, factors, plan.chart), plan.chart.decimals)
    if direction is None:
        return None
    text = trend_phrase(
        plan.scope,
        plan.subject,
        direction,
        plan.figure_number,
        plan.year,
        source_document=plan.source_document,
        source_paragraph=plan.source_paragraph,
    )
    return Paragraph(plan.proto, [text]) if text else None


def _numeric_sentence(
    ds: EnergyDataset, factors: FactorTable, plan: NumericSentencePlan
) -> Paragraph | None:
    pattern = next(
        (
            item.pattern
            for item in phrase_bank()
            if item.source_document == plan.source_document
            and item.paragraph == plan.source_paragraph
            and item.direction == "value"
        ),
        None,
    )
    if pattern is None or pattern.count("{number}") != 1 or "{year}" not in pattern:
        return None
    number, fact = value(ds, factors, plan.metric, plan.year)
    before, after = pattern.replace("{year}", str(plan.year)).split("{number}")
    return Paragraph(
        plan.proto,
        [before, Num(number, plan.decimals, fact=fact, grouping=plan.grouping), after],
    )


def analyze(
    ds: EnergyDataset, factors: FactorTable, plans: tuple[SectionPlan, ...]
) -> tuple[AnalysisSection, ...]:
    """Return ordered, typed blocks; workflows choose and locate document prototypes."""
    if len({plan.id for plan in plans}) != len(plans):
        raise ValueError("section ids must be unique")
    stages = (
        "production",
        "carrier",
        "equivalent",
        "conclusions",
        "specific",
        "intensity",
        "environment",
    )
    ordered = sorted(plans, key=lambda plan: stages.index(plan.stage))
    result: list[AnalysisSection] = []
    for plan in ordered:
        blocks: list[Block] = []
        for item in plan.items:
            if isinstance(item, TablePlan):
                blocks.append(_table(ds, factors, item))
            elif isinstance(item, MatrixTablePlan):
                blocks.append(_matrix_table(ds, factors, item))
            elif isinstance(item, ChartPlan):
                blocks.append(_chart(ds, factors, item))
            elif isinstance(item, NumericSentencePlan):
                sentence = _numeric_sentence(ds, factors, item)
                if sentence is not None:
                    blocks.append(sentence)
            else:
                sentence = _sentence(ds, factors, item)
                if sentence is not None:
                    blocks.append(sentence)
        result.append(AnalysisSection(plan.id, tuple(blocks)))
    return tuple(result)
