"""A resource's monthly tables, then for a raw resource its annual list and variable factors."""

from __future__ import annotations

from dataclasses import replace

from ema.audit.chapter_four_annual import annual as _annual
from ema.audit.chapter_four_annual import annual_carrier_table, annual_only_sentence
from ema.audit.chapter_four_comments import (
    FACTOR_LEAD,
    RESOURCE,
    annual_list,
    factor_blocks,
    period,
    table_lead,
)
from ema.consumption_analysis.analysis import Metric, SectionPlan, TablePlan, analyze
from ema.core.office.blocks import Block, Caption, Missing, Num, Paragraph, Ref, Segment, Table
from ema.core.office.missing_text import TABLE_MISSING_NOTE, TABLE_MISSING_TEXT
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset, annual_only

TITLES = {
    Carrier.electricity_grid: "Consumul de energie electrică din rețea",
    Carrier.electricity_pv: "Consumul de energie electrică fotovoltaică",
    Carrier.natural_gas: "Consumul de gaze naturale",
    Carrier.diesel: "Consumul de motorină",
    Carrier.petrol: "Consumul de benzină",
    Carrier.lpg: "Consumul de GPL",
    Carrier.fuel_oil: "Consumul de păcură",
    Carrier.clu: "Consumul de CLU",
    Carrier.coal: "Consumul de cărbune",
    Carrier.coke: "Consumul de cocs",
    Carrier.wood: "Consumul de lemn",
    Carrier.biomass: "Consumul de biomasă",
    Carrier.sunflower_husks: "Consumul de coji de floarea soarelui",
    Carrier.biogas: "Consumul de biogaz",
    Carrier.ctl: "Consumul de CTL",
    Carrier.purchased_heat: "Consumul de energie termică achiziționată",
    Carrier.water_potable: "Consumul de apă potabilă",
    Carrier.water_industrial: "Consumul de apă industrială",
    Carrier.water_storm: "Consumul de apă pluvială",
}
ELECTRIC = frozenset({Carrier.electricity_grid})
PV = frozenset({Carrier.electricity_pv})
GAS = frozenset({Carrier.natural_gas})
FUEL = frozenset({Carrier.diesel, Carrier.petrol, Carrier.lpg, Carrier.fuel_oil, Carrier.clu})


def monthly_tables(  # noqa: PLR0913
    dataset: EnergyDataset,
    factors: FactorTable,
    section: str,
    metric: Metric,
    years: tuple[int, ...],
    label: str | list[Segment],
    *,
    unit: str,
    subject: str,
    totals: bool = True,
) -> list[Block]:
    """Her shape: one caption over a January-June and a July-December table, a row per year."""
    stage = (
        "production"
        if metric.kind == "production"
        else "equivalent"
        if metric.kind in {"tep", "tep_total"}
        else "carrier"
    )
    caption_id = f"{section}:{metric.carriers}:{metric.product}"
    result: list[Block] = [
        table_lead(caption_id, f"evoluția lunară a {subject} {period(years)}"),
        Caption(
            "caption",
            "tab",
            caption_id,
            [
                "Tabelul ",
                Ref("tab", caption_id),
                ". ",
                *([label] if isinstance(label, str) else label),
                f" ({unit})" if unit else "",
            ],
        ),
    ]
    tables: list[Table] = []
    for first, proto in ((1, "months_first"), (7, "months_second")):
        metrics = tuple(replace(metric, month=month) for month in range(first, first + 6))
        plan = TablePlan(proto, metrics, years, grouping=True)
        table = analyze(dataset, factors, (SectionPlan(section, stage, (plan,)),))[0].blocks[0]
        assert isinstance(table, Table)
        tables.append(replace(table, missing_text=TABLE_MISSING_TEXT))
    result.extend(tables)
    if any(
        isinstance(segment, Num) and segment.value is None
        for table in tables
        for row in table.rows
        for cell in row
        for segment in cell
    ):
        result.append(Missing("body", TABLE_MISSING_NOTE))
    if totals:
        result.extend(_annual(dataset, factors, metric, years, unit, "Total anual"))
    return result


def resource_blocks(
    dataset: EnergyDataset,
    factors: FactorTable,
    section: str,
    allowed: frozenset[Carrier],
    *,
    equivalent: bool = False,
    factor_text: str | None = None,
) -> list[Block]:
    """A resource's tables per carrier; a raw resource then lists its annual values and its
    variable factors (#162 D3-D4): fuels share one chart, so their lists follow all tables."""
    result: list[Block] = []
    lists: list[Block] = []
    listed = section in FACTOR_LEAD
    for carrier in dataset.carriers:
        if carrier not in allowed:
            continue
        years = tuple(year for year in dataset.years if year in dataset.carriers[carrier])
        if not years:
            continue
        label = TITLES[carrier]
        result.append(Paragraph("body", [label]))
        metric = Metric("tep" if equivalent else "carrier", (carrier,))
        series = dataset.carriers[carrier][years[0]]
        reading = series.annual or next(iter(series.months.values()), None)
        unit = "tep" if equivalent else reading.unit if reading else ""
        subject = ("consumului echivalent de " if equivalent else "consumului de ") + RESOURCE[
            carrier
        ]
        if annual_only(dataset.carriers[carrier]):
            result.append(annual_only_sentence(carrier))
            result.extend(
                annual_carrier_table(
                    dataset,
                    factors,
                    metric,
                    years,
                    unit,
                    label=label,
                    section=section,
                    subject=subject,
                )
            )
            if not listed:
                result.extend(_annual(dataset, factors, metric, years, unit, "Total anual"))
        else:
            result.extend(
                monthly_tables(
                    dataset,
                    factors,
                    section,
                    metric,
                    years,
                    label,
                    unit=unit,
                    subject=subject,
                    totals=not listed,
                )
            )
        if listed:
            carrier_list = annual_list(dataset, factors, carrier, years, unit)
            (lists if section == "ch4.carburant" else result).extend(carrier_list)
    if not result:
        return [Missing("body", "[de completat]")]
    if listed:
        result.extend(lists)
        result.extend(factor_blocks(section, factor_text))
    return result
