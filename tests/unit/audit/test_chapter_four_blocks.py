"""Chapter four plans show sourced calculations and visible missing sections."""

from ema.audit.chapter_four_blocks import chapter_four_blocks
from ema.core.office.blocks import Caption, Missing, Num, Paragraph, Table
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
