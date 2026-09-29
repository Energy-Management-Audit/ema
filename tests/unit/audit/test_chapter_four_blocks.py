"""Chapter four plans show sourced calculations and visible missing sections."""

import pytest

from ema.audit.chapter_four_blocks import chapter_four_blocks
from ema.audit.chapter_four_charts import chart_blocks
from ema.core.office.blocks import Caption, Missing, NativeChart, Num, Paragraph, Table
from ema.core.office.missing_text import TABLE_MISSING_NOTE, TABLE_MISSING_TEXT
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading


def test_chapter_four_has_source_backed_tables_and_missing_sections() -> None:
    dataset = EnergyDataset(
        (2025,),
        {
            Carrier.electricity_grid: {
                2025: CarrierSeries({1: Reading(10, "MWh")}, Reading(10, "MWh"))
            },
            Carrier.natural_gas: {2025: CarrierSeries(annual=Reading(20, "MWh"))},
            Carrier.diesel: {2025: CarrierSeries(annual=Reading(1, "t"))},
            Carrier.water_potable: {2025: CarrierSeries(annual=Reading(3, "m3"))},
        },
        {"product": {2025: CarrierSeries(annual=Reading(100, "t"))}},
        {"product": "t"},
        {2025: Reading(10_000, "lei")},
    )
    blocks = chapter_four_blocks(dataset, FACTORS_2026)
    headings = [
        block.proto
        for block in blocks
        if isinstance(block, Paragraph) and block.proto.startswith("heading:")
    ]
    assert "heading:ch4.electricitate" in headings
    assert "heading:ch4.gaz" in headings
    assert "heading:ch4.mediu" in headings
    assert sum(isinstance(block, Table) for block in blocks) >= 10
    assert sum(isinstance(block, Caption) for block in blocks) >= 10
    assert any(isinstance(block, Missing) for block in blocks)
    annual = [
        segment
        for block in blocks
        if isinstance(block, Paragraph)
        for segment in block.segments
        if isinstance(segment, Num)
    ]
    assert any(number.value == 10 and number.unit == "MWh" for number in annual)
    assert any(number.value == 20 and number.unit == "MWh" for number in annual)


def test_empty_dataset_marks_unavailable_values() -> None:
    blocks = chapter_four_blocks(EnergyDataset((2025,), {}), FACTORS_2026)
    assert any(isinstance(block, Missing) and block.text == "[de completat]" for block in blocks)
    assert not any(isinstance(block, Num) and block.value for block in blocks)


def test_grouped_tables_source_labels_and_scaled_value_lines() -> None:
    dataset = EnergyDataset(
        (2025,),
        {Carrier.electricity_grid: {2025: CarrierSeries(annual=Reading(10, "MWh"))}},
        {
            "lacuri_si_vopsele": {
                2025: CarrierSeries({1: Reading(1234.5, "kg")}, Reading(2000, "kg"))
            }
        },
        {"lacuri_si_vopsele": "kg"},
        {2025: Reading(1_000_000, "lei")},
        production_name={"lacuri_si_vopsele": "Lacuri și vopsele"},
    )
    blocks = chapter_four_blocks(dataset, FACTORS_2026, client="Atelier Exemplu SRL")
    tables = [block for block in blocks if isinstance(block, Table)]
    number = tables[0].rows[0][1][0]
    assert isinstance(number, Num) and number.grouping and number.value == 1234.5
    title = next(block for block in blocks if isinstance(block, Caption))
    assert "".join(segment for segment in title.segments[3:] if isinstance(segment, str)) == (
        "Centralizator al producției lunare înregistrate de către Atelier Exemplu SRL "
        "– Lacuri și vopsele/lună"
    )
    assert not any(isinstance(b, Paragraph) and b.segments == ["Lacuri și vopsele"] for b in blocks)
    lines = [
        b
        for b in blocks
        if isinstance(b, Paragraph)
        and b.segments[0] == "pentru anul 2025 s-a înregistrat o valoare de "
    ]
    specific = next(
        b.segments[1]
        for b in lines
        if isinstance(b.segments[1], Num) and b.segments[1].unit == "tep/t"
    )
    intensity = next(
        b.segments[1]
        for b in lines
        if isinstance(b.segments[1], Num) and b.segments[1].unit == "tep/mil lei"
    )
    assert isinstance(specific, Num) and specific.value == pytest.approx(0.43)
    assert isinstance(intensity, Num) and intensity.value == pytest.approx(0.86)


def test_gpl_total_without_readings_is_missing_but_entered_zero_stays_zero() -> None:
    dataset = EnergyDataset(
        (2024, 2025),
        {
            Carrier.lpg: {
                2024: CarrierSeries(annual=Reading(None, "t")),
                2025: CarrierSeries(annual=Reading(0, "t")),
            }
        },
    )
    blocks = chapter_four_blocks(dataset, FACTORS_2026)
    totals = [
        b.segments[1]
        for b in blocks
        if isinstance(b, Paragraph) and str(b.segments[0]).startswith("Total anual")
    ]
    assert isinstance(totals[0], Num) and totals[0].value is None
    assert isinstance(totals[1], Num) and totals[1].value == 0


def test_per_lei_specific_values_and_charts_scale_to_per_million_lei() -> None:
    dataset = EnergyDataset(
        (2025,),
        {Carrier.electricity_grid: {2025: CarrierSeries(annual=Reading(10, "MWh"))}},
        {"cifra_afaceri": {2025: CarrierSeries(annual=Reading(1_000_000, "lei"))}},
        {"cifra_afaceri": "lei"},
        production_name={"cifra_afaceri": "Cifra de afaceri"},
    )
    blocks = chapter_four_blocks(dataset, FACTORS_2026)
    values = [
        segment
        for block in blocks
        if isinstance(block, Paragraph)
        for segment in block.segments
        if isinstance(segment, Num) and segment.unit == "tep/mil lei"
    ]
    assert values and values[0].value == pytest.approx(0.86)


def test_missing_specific_line_uses_the_year_and_a_missing_block():
    dataset = EnergyDataset(
        (2025,),
        {Carrier.electricity_grid: {2025: CarrierSeries(annual=Reading(None, "MWh"))}},
        {"product": {2025: CarrierSeries(annual=Reading(100, "kg"))}},
        {"product": "kg"},
    )
    blocks = chapter_four_blocks(dataset, FACTORS_2026)
    assert Missing("body", "pentru anul 2025: date indisponibile;") in blocks
    assert not any(
        isinstance(block, Paragraph) and "date indisponibile" in str(block.segments)
        for block in blocks
    )


def test_lei_title_and_unavailable_metadata_use_typed_missing_segments():
    dataset = EnergyDataset(
        (2025,),
        {},
        {"turnover": {2025: CarrierSeries(annual=Reading(100, "lei"))}},
        {"turnover": "lei"},
    )
    blocks = chapter_four_blocks(dataset, FACTORS_2026, client="Atelier Exemplu SRL")
    caption = next(block for block in blocks if isinstance(block, Caption))
    assert "".join(segment for segment in caption.segments[3:] if isinstance(segment, str)) == (
        "Centralizator al cifrei lunare de afaceri înregistrate de către Atelier Exemplu SRL "
        "– lei/lună"
    )
    dataset.production_unit["turnover"] = "kg"
    caption = next(
        block for block in chapter_four_blocks(dataset, FACTORS_2026) if isinstance(block, Caption)
    )
    assert (
        sum(isinstance(segment, Num) and segment.value is None for segment in caption.segments) == 2
    )
    assert all(
        "date indisponibile" not in segment
        for segment in caption.segments
        if isinstance(segment, str)
    )


def test_product_units_with_a_slash_are_not_scaled_as_specific_consumption():
    dataset = EnergyDataset(
        (2025,),
        {},
        {"product": {2025: CarrierSeries(annual=Reading(2, "items/kg"))}},
        {"product": "items/kg"},
        production_name={"product": "Product"},
    )
    blocks = chapter_four_blocks(dataset, FACTORS_2026)
    total = next(
        block.segments[1]
        for block in blocks
        if isinstance(block, Paragraph) and str(block.segments[0]).startswith("Total anual")
    )
    charts, _ = chart_blocks("ch4.productie", dataset, FACTORS_2026, "Client")
    chart = next(block for block in charts if isinstance(block, NativeChart))
    assert total.value == chart.series[0].values[0] == 2
    assert total.unit == "items/kg" and chart.column_axis_title == "items/kg/an"


@pytest.mark.parametrize(
    ("unit", "table_subject", "figure_subject", "suffix"),
    (
        ("t ulei", "producției lunare", "producției lunare", "Ulei/lună"),
        ("mii lei", "cifrei lunare de afaceri", "cifrei lunare de afaceri", "mii lei/lună"),
    ),
)
def test_production_titles_classify_lei_as_a_word_and_keep_source_unit(
    unit, table_subject, figure_subject, suffix
):
    dataset = EnergyDataset(
        (2025,),
        {},
        {"product": {2025: CarrierSeries({1: Reading(2, unit)}, Reading(2, unit))}},
        {"product": unit},
        production_name={"product": "Ulei"},
    )
    table = next(
        block
        for block in chapter_four_blocks(dataset, FACTORS_2026, client="Client")
        if isinstance(block, Caption)
    )
    title = "".join(segment for segment in table.segments if isinstance(segment, str))
    assert f"Centralizator al {table_subject} înregistrate de către Client" in title
    assert title.endswith(suffix)
    charts, _ = chart_blocks("ch4.productie", dataset, FACTORS_2026, "Client")
    caption = next(block for block in charts if isinstance(block, Paragraph))
    assert f"Evoluția lunară a {figure_subject}" in caption.segments[0]


def test_monthly_missing_note_follows_only_the_table_with_missing_cells():
    dataset = EnergyDataset(
        (2025,),
        {
            Carrier.electricity_grid: {
                2025: CarrierSeries(
                    {month: Reading(month, "MWh") for month in range(1, 7)}, Reading(21, "MWh")
                )
            }
        },
    )
    blocks = chapter_four_blocks(dataset, FACTORS_2026)
    start = next(
        i
        for i, b in enumerate(blocks)
        if isinstance(b, Paragraph) and b.proto == "heading:ch4.electricitate"
    )
    end = next(
        i
        for i in range(start + 1, len(blocks))
        if isinstance(blocks[i], Paragraph) and blocks[i].proto.startswith("heading:")
    )
    section = blocks[start:end]
    tables = [(i, b) for i, b in enumerate(section) if isinstance(b, Table)]
    assert len(tables) == 2
    assert all(b.missing_text == "—" and ord(b.missing_text) == 0x2014 for _, b in tables)
    first, second = (i for i, _ in tables)
    assert not isinstance(section[first + 1], Missing)
    assert section[second + 1] == Missing("body", "—: date indisponibile")
    assert [b for b in section if isinstance(b, Missing)] == [Missing("body", TABLE_MISSING_NOTE)]
    assert TABLE_MISSING_TEXT == "—"


def test_specific_product_name_is_present_only_for_multiple_active_products():
    dataset = EnergyDataset(
        (2025,),
        {Carrier.electricity_grid: {2025: CarrierSeries(annual=Reading(10, "MWh"))}},
        {key: {2025: CarrierSeries(annual=Reading(100, "kg"))} for key in ("one", "two")},
        {"one": "kg", "two": "kg"},
        production_name={"one": "Produs întâi", "two": "Produs al doilea"},
    )
    blocks = chapter_four_blocks(dataset, FACTORS_2026)
    lines = [
        block
        for block in blocks
        if isinstance(block, Paragraph)
        and any(isinstance(segment, Num) and segment.unit == "tep/t" for segment in block.segments)
    ]
    assert {line.segments[0] for line in lines} == {"Produs întâi", "Produs al doilea"}
    del dataset.production["two"]
    lines = [
        block
        for block in chapter_four_blocks(dataset, FACTORS_2026)
        if isinstance(block, Paragraph)
        and any(isinstance(segment, Num) and segment.unit == "tep/t" for segment in block.segments)
    ]
    assert all(
        line.segments[0] == "pentru anul 2025 s-a înregistrat o valoare de " for line in lines
    )
