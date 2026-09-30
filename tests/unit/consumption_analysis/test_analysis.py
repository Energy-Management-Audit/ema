"""S7 calculations use data facts and the prototype's displayed precision."""

from dataclasses import replace

from ema.consumption_analysis.analysis import (
    ChartPlan,
    Metric,
    NumericSentencePlan,
    SectionPlan,
    TablePlan,
    TrendPlan,
    analyze,
    resolve_value,
)
from ema.consumption_analysis.phrases import (
    phrase_bank,
    trend_direction,
)
from ema.core.office.blocks import NativeChart, Num, Paragraph, Table
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import Factor, FactorTable
from ema.energy_data.model import CarrierSeries, EnergyDataset, FiledValue, Reading


def _dataset() -> EnergyDataset:
    return EnergyDataset(
        (2023, 2024, 2025),
        {
            Carrier.natural_gas: {
                year: CarrierSeries(
                    {month: Reading(float(index + month), "MWh") for month in range(1, 13)},
                    Reading(float(index * 100), "MWh"),
                )
                for index, year in enumerate((2023, 2024, 2025), 1)
            }
        },
    )


def _factors() -> FactorTable:
    return FactorTable(
        "fixture",
        2023,
        (Factor(Carrier.natural_gas, "MWh", 0.086, "fixture"),),
        (Factor(Carrier.natural_gas, "MWh", 0.1787, "fixture"),),
    )


def test_ordered_blocks_use_facts_and_audit_phrase() -> None:
    ds = _dataset()
    chart = ChartPlan(
        "chart",
        "word/charts/chart1.xml",
        "gaz",
        Metric("carrier", (Carrier.natural_gas,)),
        ds.years,
        tuple(map(str, ds.years)),
    )
    table = TablePlan(
        "table",
        tuple(Metric("carrier", (Carrier.natural_gas,), month=month) for month in range(1, 7)),
        ds.years,
    )
    sections = analyze(
        ds,
        _factors(),
        (
            SectionPlan("ch4.echiv_gaz", "equivalent", ()),
            SectionPlan(
                "ch4.gaz",
                "carrier",
                (table, chart, TrendPlan("body", "consumului de gaz natural", "4.3", chart)),
            ),
        ),
    )
    assert [section.id for section in sections] == ["ch4.gaz", "ch4.echiv_gaz"]
    built_table, built_chart, sentence = sections[0].blocks
    assert isinstance(built_table, Table)
    assert isinstance(built_table.rows[0][1][0], Num)
    assert built_table.rows[0][1][0].value == 2
    assert built_table.rows[0][1][0].fact == "carrier.natural_gas.2023.01"
    assert isinstance(built_chart, NativeChart)
    assert built_chart.series[0].values == [100, 200, 300]
    assert isinstance(sentence, Paragraph)
    assert "creștere" in sentence.segments[0]
    assert "4.3" in sentence.segments[0]


def test_missing_input_keeps_missing_cell_and_omits_unsupported_sentence() -> None:
    ds = EnergyDataset((2023, 2024), {Carrier.natural_gas: {2023: CarrierSeries()}})
    chart = ChartPlan(
        "chart",
        "word/charts/chart1.xml",
        "gaz",
        Metric("carrier", (Carrier.natural_gas,)),
        ds.years,
        ("2023", "2024"),
    )
    section = analyze(
        ds,
        _factors(),
        (
            SectionPlan(
                "ch4.gaz",
                "carrier",
                (
                    TablePlan("table", (Metric("carrier", (Carrier.natural_gas,)),), ds.years),
                    chart,
                    TrendPlan("body", "consumului de gaz natural", "4.3", chart),
                ),
            ),
        ),
    )[0]
    assert len(section.blocks) == 2
    table = section.blocks[0]
    assert isinstance(table, Table)
    assert isinstance(table.rows[0][1][0], Num)
    assert table.rows[0][1][0].value is None


def test_phrase_bank_is_anonymous_and_trend_uses_displayed_precision() -> None:
    patterns = phrase_bank()
    assert {pattern.source_document for pattern in patterns} == {
        *(f"audit-0{index}" for index in range(1, 6)),
        *(f"piee-0{index}" for index in range(1, 4)),
    }
    assert all(
        "{figure_number}" in pattern.pattern or "{number}" in pattern.pattern
        for pattern in patterns
    )
    assert trend_direction([1.001, 1.002, 1.003], 2) == "constant"
    assert trend_direction([1.001, 1.002, 1.003], 3) == "growth"


def test_sourced_numeric_sentence_uses_a_calculated_fact() -> None:
    ds = EnergyDataset(
        (2023,),
        {Carrier.natural_gas: {2023: CarrierSeries(annual=Reading(100, "MWh"))}},
        {"turnover_specific": {2023: CarrierSeries(annual=Reading(100, "mil lei"))}},
        {"turnover_specific": "mil lei"},
    )
    plan = NumericSentencePlan(
        "body",
        Metric("specific", (Carrier.natural_gas,), "turnover_specific"),
        2023,
        "audit-02",
        948,
        decimals=2,
    )
    section = analyze(ds, _factors(), (SectionPlan("specific", "specific", (plan,)),))[0]
    sentence = section.blocks[0]
    assert isinstance(sentence, Paragraph)
    assert sentence.segments[0].startswith("pentru anul 2023")
    assert isinstance(sentence.segments[1], Num)
    assert sentence.segments[1].value == 0.086
    assert sentence.segments[1].fact == "carrier.natural_gas.2023+production.turnover_specific.2023"


def largest_share(shares: dict[str, float | None]) -> str | None:
    present = [(name, value) for name, value in shares.items() if value is not None]
    return sorted(present, key=lambda item: (-item[1], item[0]))[0][0] if present else None


def notable_month(values: dict[int, float | None], *, high: bool) -> int | None:
    present = [(month, value) for month, value in values.items() if value is not None]
    if not present:
        return None
    return sorted(present, key=lambda item: ((-1 if high else 1) * item[1], item[0]))[0][0]


def test_largest_share_and_notable_month_break_ties_deterministically() -> None:
    assert largest_share({"diesel": 50, "gas": 50, "petrol": None}) == "diesel"
    assert notable_month({1: 5, 2: 5, 3: None}, high=True) == 1
    assert notable_month({1: 5, 2: 5, 3: None}, high=False) == 1


def test_filed_indicators_recompute_when_inventory_complete_and_expose_conflicts() -> None:
    ds = EnergyDataset(
        (2025,),
        {
            Carrier.electricity_grid: {2025: CarrierSeries(annual=Reading(10, "MWh"))},
            Carrier.natural_gas: {2025: CarrierSeries(annual=Reading(20, "MWh"))},
        },
        turnover_lei={2025: Reading(1_000_000, "lei")},
        filed_indicators={
            "intensity": {2025: FiledValue(0.0300, "tep/1000 lei", 4, "synthetic:1")},
            "co2.total": {2025: FiledValue(59, "t CO₂", 0, "synthetic:2")},
        },
    )
    factors = FactorTable(
        "synthetic",
        2025,
        (
            Factor(Carrier.electricity_grid, "MWh", 1, "synthetic"),
            Factor(Carrier.natural_gas, "MWh", 1, "synthetic"),
        ),
        (
            Factor(Carrier.electricity_grid, "MWh", 2, "synthetic"),
            Factor(Carrier.natural_gas, "MWh", 2, "synthetic"),
        ),
    )
    intensity = resolve_value(ds, factors, Metric("intensity"), 2025)
    emissions = resolve_value(ds, factors, Metric("co2"), 2025)
    assert (intensity.value, intensity.origin, intensity.conflict) == (0.03, "recomputed", False)
    assert (emissions.value, emissions.origin, emissions.conflict) == (60, "recomputed", True)
    filed = resolve_value(
        replace(ds, energy_inventory_complete=False), factors, Metric("intensity"), 2025
    )
    assert (filed.value, filed.origin, filed.fact) == (0.03, "filed", "filed:synthetic:1")
