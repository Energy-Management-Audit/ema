"""Ch. 4: totals from the printed components, readable specific values, emissions per carrier."""

from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.audit.chapter_four_blocks import chapter_four_blocks
from ema.audit.chapter_four_chart_text import readable_unit
from ema.audit.chapter_four_charts import chart_blocks
from ema.audit.totals_review import record_totals_review, totals_issues
from ema.consumption_analysis.analysis import Metric, resolve_value, value
from ema.core.office.blocks import Block, Missing, NativeChart, Num, Paragraph, Table
from ema.core.review.models import Field
from ema.core.workspace import Workspace
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import AUDIT_FACTORS_2026, FACTORS_2026
from ema.energy_data.model import CarrierSeries, EnergyDataset, FiledValue, Reading

CLIENT = "Atelier Exemplu SRL"


def _dataset(*, lpg: Reading | None = None, filed_total: float | None = 99.0) -> EnergyDataset:
    carriers = {
        Carrier.electricity_grid: {2025: CarrierSeries(annual=Reading(100, "MWh"))},
        Carrier.electricity_pv: {2025: CarrierSeries(annual=Reading(5, "MWh"))},
        Carrier.natural_gas: {2025: CarrierSeries(annual=Reading(200, "MWh"))},
        Carrier.diesel: {2025: CarrierSeries(annual=Reading(10, "t"))},
    }
    filed: dict[str, dict[int, FiledValue]] = {}
    if lpg is not None:
        carriers[Carrier.lpg] = {2025: CarrierSeries(annual=lpg)}
        filed["tep.lpg"] = {2025: FiledValue(0.0, "tep", 2, "Sheet!A1")}
    if filed_total is not None:
        filed["tep_total"] = {2025: FiledValue(filed_total, "tep", 2, "Sheet!A2")}
    return EnergyDataset(
        (2025,),
        carriers,
        {"product": {2025: CarrierSeries(annual=Reading(1_000_000, "kg"))}},
        {"product": "kg"},
        {2025: Reading(10_000_000, "lei")},
        filed_indicators=filed,
    )


def _section(blocks: list[Block], section: str) -> list[Block]:
    start = next(
        i
        for i, block in enumerate(blocks)
        if isinstance(block, Paragraph) and block.proto == f"heading:{section}"
    )
    end = next(
        (
            i
            for i in range(start + 1, len(blocks))
            if isinstance(blocks[i], Paragraph) and blocks[i].proto.startswith("heading:")  # type: ignore[union-attr]
        ),
        len(blocks),
    )
    return blocks[start + 1 : end]


def _numbers(blocks: list[Block], unit: str) -> list[Num]:
    return [
        segment
        for block in blocks
        if isinstance(block, Paragraph)
        for segment in block.segments
        if isinstance(segment, Num) and segment.unit == unit
    ]


def test_printed_total_equals_the_sum_of_printed_components_not_the_filed_total() -> None:
    blocks = chapter_four_blocks(_dataset(), FACTORS_2026)
    parts = [
        number.value
        for section in (
            "ch4.echiv_electric",
            "ch4.echiv_pv",
            "ch4.echiv_gaz",
            "ch4.echiv_carburant",
        )
        for number in _numbers(_section(blocks, section), "tep")
    ]
    (total,) = _numbers(_section(blocks, "ch4.echiv_total"), "tep")
    assert len(parts) == 4
    assert total.value == pytest.approx(sum(p for p in parts if p is not None))
    assert total.value != 99.0
    (intensity,) = _numbers(_section(blocks, "ch4.intensitate"), "tep/mil lei")
    assert intensity.value == pytest.approx(total.value / 10.0)


def test_a_carrier_with_a_filed_tep_but_no_reading_blanks_the_total_instead_of_mixing() -> None:
    dataset = _dataset(lpg=Reading(None, "t"))
    blocks = chapter_four_blocks(dataset, FACTORS_2026)
    lpg = [n for n in _numbers(_section(blocks, "ch4.echiv_carburant"), "tep") if n.value is None]
    assert lpg, "GPL prints as missing, not as the filed 0"
    (total,) = _numbers(_section(blocks, "ch4.echiv_total"), "tep")
    assert total.value is None
    assert not _numbers(_section(blocks, "ch4.intensitate"), "tep/mil lei")
    assert any(isinstance(b, Missing) for b in _section(blocks, "ch4.intensitate"))
    assert not _numbers(_section(blocks, "ch4.specific_total"), "tep/mii tone")


def test_piee_keeps_its_filed_fallback() -> None:
    dataset = _dataset(lpg=Reading(None, "t"))
    metric = Metric("tep_total")
    assert value(dataset, FACTORS_2026, metric, 2025)[0] == 99.0
    assert resolve_value(dataset, FACTORS_2026, metric, 2025).origin == "filed"
    assert value(dataset, FACTORS_2026, metric, 2025, filed=False)[0] is None
    specific = Metric("specific", product="product")
    assert value(dataset, FACTORS_2026, specific, 2025)[0] == pytest.approx(99.0 / 1_000_000)
    assert value(dataset, FACTORS_2026, specific, 2025, filed=False)[0] is None


@pytest.mark.parametrize(
    ("unit", "scale", "numbers", "expected"),
    [
        ("tep/t", 1000.0, [3.6e-5], ("tep/mii tone", 1_000_000.0)),
        ("tep/t lacuri", 1000.0, [5e-5, 0.4], ("tep/mii tone lacuri", 1_000_000.0)),
        ("tep/tone", 1.0, [0.04], ("tep/mii tone", 1000.0)),
        ("tep/t", 1.0, [0.5, 0.09], ("tep/mii tone", 1000.0)),
        ("tep/t", 1.0, [0.1, 2.0], ("tep/t", 1.0)),
        ("tep/t", 1.0, [0.0, None], ("tep/t", 1.0)),
        ("tep/buc", 1.0, [0.01], ("tep/buc", 1.0)),
    ],
)
def test_readable_unit_goes_per_thousand_tonnes_below_one_tenth(
    unit: str, scale: float, numbers: list[float | None], expected: tuple[str, float]
) -> None:
    assert readable_unit(unit, scale, numbers) == expected


def test_specific_consumption_prints_per_thousand_tonnes_in_text_and_chart() -> None:
    dataset = _dataset()
    blocks = chapter_four_blocks(dataset, FACTORS_2026)
    (printed,) = _numbers(_section(blocks, "ch4.specific_total"), "tep/mii tone")
    components = [
        value(dataset, FACTORS_2026, Metric("tep", (c,)), 2025)[0]
        for c in (
            Carrier.electricity_grid,
            Carrier.electricity_pv,
            Carrier.natural_gas,
            Carrier.diesel,
        )
    ]
    assert printed.value == pytest.approx(sum(c for c in components if c is not None))
    charts, _ = chart_blocks("ch4.specific_total", dataset, FACTORS_2026, CLIENT)
    (chart,) = [block for block in charts if isinstance(block, NativeChart)]
    assert chart.column_axis_title == "tep/mii tone"
    assert chart.series[0].values == [pytest.approx(printed.value)]


def test_specific_consumption_keeps_tonnes_when_it_is_readable() -> None:
    dataset = _dataset()
    big = EnergyDataset(
        dataset.years,
        dataset.carriers,
        {"product": {2025: CarrierSeries(annual=Reading(100, "kg"))}},
        {"product": "kg"},
        dataset.turnover_lei,
    )
    printed = _numbers(
        _section(chapter_four_blocks(big, FACTORS_2026), "ch4.specific_total"), "tep/t"
    )
    assert [round(n.value or 0, 2) for n in printed] == [363.8]


def _emissions(blocks: list[Block]) -> Table:
    (table,) = [b for b in _section(blocks, "ch4.mediu") if isinstance(b, Table)]
    return table


def _rows(table: Table) -> dict[str, Num | str]:
    return {str(row[0][0]): row[1][0] for row in table.rows if isinstance(row[1][0], Num | str)}


def test_emissions_one_row_per_carrier_with_audit_factors_and_total() -> None:
    table = _emissions(chapter_four_blocks(_dataset(), AUDIT_FACTORS_2026))
    rows = _rows(table)
    assert list(rows) == ["Energie electrică din SEN", "Gaze naturale", "Motorină", "Total"]
    assert table.header == [["Sursa", "2025"]]
    assert table.missing_text == "n.d."
    assert rows["Energie electrică din SEN"].value == pytest.approx(100 * 0.172)  # type: ignore[union-attr]
    assert rows["Gaze naturale"].value == pytest.approx(200 * 0.205)  # type: ignore[union-attr]
    assert rows["Motorină"].value == pytest.approx(10 * 2.91 / 0.84)  # type: ignore[union-attr]
    parts = [n.value for k, n in rows.items() if k != "Total"]  # type: ignore[union-attr]
    assert rows["Total"].value == pytest.approx(sum(p for p in parts if p is not None))  # type: ignore[union-attr]


def test_emissions_gap_marks_its_row_and_the_total_without_blanking_the_section() -> None:
    rows = _rows(
        _emissions(chapter_four_blocks(_dataset(lpg=Reading(None, "t")), AUDIT_FACTORS_2026))
    )
    assert rows["GPL"].value is None  # type: ignore[union-attr]
    assert rows["Total"].value is None  # type: ignore[union-attr]
    assert rows["Gaze naturale"].value == pytest.approx(200 * 0.205)  # type: ignore[union-attr]


def test_emissions_carrier_without_a_factor_prints_nd_on_its_row() -> None:
    rows = _rows(_emissions(chapter_four_blocks(_dataset(lpg=Reading(5, "t")), AUDIT_FACTORS_2026)))
    assert rows["GPL"].value is None  # type: ignore[union-attr]
    assert rows["Total"].value is None  # type: ignore[union-attr]


def test_audit_co2_factors_are_hers() -> None:
    by_carrier = {f.carrier: f for f in AUDIT_FACTORS_2026.co2}
    assert by_carrier[Carrier.electricity_grid].per_unit == 0.172
    assert by_carrier[Carrier.natural_gas].per_unit == 0.205
    assert by_carrier[Carrier.diesel].per_unit == pytest.approx(2.91 / 0.84)
    assert by_carrier[Carrier.petrol].per_unit == pytest.approx(2.29 / 0.77)
    assert by_carrier[Carrier.biomass].per_unit == 0
    assert [f.carrier for f in FACTORS_2026.co2][:2] == [
        Carrier.electricity_grid,
        Carrier.natural_gas,
    ]
    assert FACTORS_2026.co2_factor(Carrier.electricity_grid, "MWh", 2025).per_unit == 0.226  # type: ignore[union-attr]


def _review(tmp_path: Path, dataset: EnergyDataset) -> tuple[Workspace, str, dict[str, Field]]:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "client-x", 2025)
    record_totals_review(ws, job, dataset, FACTORS_2026, "a" * 64)
    with ws.connect() as db:
        facts = {
            str(row["key"]): Field.model_validate_json(row["data"])
            for row in db.execute("SELECT key,data FROM fields WHERE job_id=?", (job,))
        }
    return ws, job, facts


def test_a_filed_total_that_differs_is_a_conflict_that_blocks_the_final(tmp_path: Path) -> None:
    _, _, facts = _review(tmp_path, _dataset())
    field = facts["tep_total.2025"]
    assert field.confidence == "conflict"
    assert sorted(float(item.value) for item in field.alternatives) == [36.38, 99.0]
    (issue,) = totals_issues(facts)
    assert issue.code == "conflict"


def test_a_filed_total_that_matches_at_display_precision_raises_nothing(tmp_path: Path) -> None:
    _, _, facts = _review(tmp_path, _dataset(filed_total=36.38))
    assert totals_issues(facts) == []


def test_a_carrier_filed_but_not_read_is_carrier_incomplete(tmp_path: Path) -> None:
    _, _, facts = _review(tmp_path, _dataset(lpg=Reading(None, "t")))
    assert [
        (i.code, i.message) for i in totals_issues(facts) if i.code == "carrier_incomplete"
    ] == [("carrier_incomplete", "Lipseşte consumul de GPL pentru 2025.")]
    assert "tep_total.2025" not in facts
