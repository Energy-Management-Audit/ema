"""Native ch. 4 charts use table metrics, the caption contract and gaps."""

from dataclasses import replace

from ema.audit.chapter_four_charts import chapter_chart_groups, chart_blocks
from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.blocks import Missing, NativeChart, Paragraph
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading

CLIENT = "Atelier Exemplu SRL"


def _dataset() -> EnergyDataset:
    return EnergyDataset(
        (2024, 2025),
        {
            Carrier.electricity_grid: {
                2024: CarrierSeries(
                    {1: Reading(1234.5, "MWh"), 2: Reading(None, "MWh")}, Reading(1234.5, "MWh")
                ),
                2025: CarrierSeries(annual=Reading(20, "MWh")),
            },
            Carrier.electricity_pv: {2024: CarrierSeries(annual=Reading(5, "MWh"))},
            Carrier.natural_gas: {
                2024: CarrierSeries({1: Reading(None, "MWh")}, Reading(None, "MWh"))
            },
            Carrier.diesel: {2024: CarrierSeries({1: Reading(1, "t")}, Reading(1, "t"))},
            Carrier.petrol: {2024: CarrierSeries({1: Reading(2, "t")}, Reading(2, "t"))},
            Carrier.water_potable: {2024: CarrierSeries(annual=Reading(3, "m³"))},
            Carrier.water_industrial: {2024: CarrierSeries(annual=Reading(4, "m³"))},
            Carrier.water_storm: {2024: CarrierSeries(annual=Reading(5, "m³"))},
        },
        {"product": {2024: CarrierSeries({1: Reading(100, "kg")}, Reading(100, "kg"))}},
        {"product": "kg"},
        {2024: Reading(1000, "lei")},
    )


def _captions(blocks: list[object]) -> list[str]:
    return [str(block.segments[0]) for block in blocks if isinstance(block, Paragraph)]


def _charts(blocks: list[object]) -> list[NativeChart]:
    return [block for block in blocks if isinstance(block, NativeChart)]


def test_monthly_gap_caption_letters_and_skipped_variants() -> None:
    dataset = _dataset()
    electricity, _ = chart_blocks("ch4.electricitate", dataset, FACTORS_2026, CLIENT)
    assert _captions(electricity) == [
        "Fig. nr. 4.2 a) Evoluția lunară a consumului de energie electrică din SEN "
        "înregistrat de către Atelier Exemplu SRL la nivelul anului 2024",
        "Fig. nr. 4.2 c) Evoluția anuală a consumului de energie electrică din SEN "
        "înregistrat la nivelul Atelier Exemplu SRL",
    ]
    monthly, annual = _charts(electricity)
    assert (monthly.series[0].categories[0], monthly.series[0].values[:2]) == (
        "Ianuarie",
        [1234.5, None],
    )
    assert (monthly.column_axis_title, annual.column_axis_title) == ("MWh/lună", "MWh/an")
    assert annual.series[0].categories == ["2024", "2025"]
    assert _charts(chart_blocks("ch4.gaz", dataset, FACTORS_2026, CLIENT)[0]) == []
    groups, skipped = chapter_chart_groups(dataset, FACTORS_2026, CLIENT)
    assert skipped == [
        "ch4.apa:water_storm",
        "ch4.specific_apa:water_storm",
        "ch4.electricitate:2025:no_data",
        "ch4.electricitate_pv:2024:no_data",
        "ch4.gaz:2024:no_data",
        "ch4.gaz:annual:no_data",
        "ch4.apa:water_potable:2024:no_data",
        "ch4.apa:water_industrial:2024:no_data",
        "ch4.echiv_gaz:annual:no_data",
        "ch4.specific_gaz:annual:no_data",
        "ch4.specific_total:annual:no_data",
        "ch4.intensitate:annual:no_data",
    ]
    assert len(groups["ch4.apa"]) == 2


def test_fuels_share_one_chart_with_one_series_each_and_no_monthly_letter_when_absent() -> None:
    dataset = _dataset()
    blocks, _ = chart_blocks("ch4.carburant", dataset, FACTORS_2026, CLIENT)
    monthly, annual = _charts(blocks)
    assert [series.name for series in monthly.series] == [
        "Consumul de motorină",
        "Consumul de benzină",
    ]
    assert [series.values[0] for series in annual.series] == [1, 2]
    assert _captions(blocks)[0].startswith(
        "Fig. nr. 4.5 a) Evoluția lunară a consumului de carburant"
    )
    water, _ = chart_blocks("ch4.apa", dataset, FACTORS_2026, CLIENT)
    assert _captions(water) == [
        "Fig. nr. 4.6 b) Evoluția anuală a consumului de apă înregistrat "
        "la nivelul Atelier Exemplu SRL",
        "Fig. nr. 4.7 b) Evoluția anuală a consumului de apă industrială "
        "înregistrat la nivelul Atelier Exemplu SRL",
    ]


def test_product_and_mixed_fuel_units_skip_without_a_chart() -> None:
    dataset = _dataset()
    second = dict(dataset.production)
    second["second"] = {2024: CarrierSeries(annual=Reading(2, "kg"))}
    units = dict(dataset.production_unit)
    units["second"] = "kg"
    multiple = EnergyDataset(dataset.years, dataset.carriers, second, units)
    assert chart_blocks("ch4.productie", multiple, FACTORS_2026, CLIENT) == (
        [],
        ["ch4.productie:products"],
    )
    assert chart_blocks("ch4.specific_total", multiple, FACTORS_2026, CLIENT) == (
        [],
        ["ch4.specific_total:products"],
    )
    carriers = dict(dataset.carriers)
    carriers[Carrier.petrol] = {2024: CarrierSeries(annual=Reading(2, "l"))}
    mixed = EnergyDataset(dataset.years, carriers, dataset.production, dataset.production_unit)
    assert chart_blocks("ch4.carburant", mixed, FACTORS_2026, CLIENT) == (
        [],
        ["ch4.carburant:units"],
    )


def test_every_sourced_monthly_caption_uses_the_contract() -> None:
    def reading(amount: float, unit: str) -> dict[int, CarrierSeries]:
        return {2025: CarrierSeries({1: Reading(amount, unit)}, Reading(amount, unit))}

    dataset = EnergyDataset(
        (2025,),
        {
            Carrier.electricity_grid: reading(10, "MWh"),
            Carrier.natural_gas: reading(20, "MWh"),
            Carrier.diesel: reading(1, "t"),
            Carrier.petrol: reading(2, "t"),
            Carrier.water_potable: reading(3, "m³"),
            Carrier.water_industrial: reading(4, "m³"),
        },
        {"product": reading(100, "lei")},
        {"product": "lei"},
        {2025: Reading(1000, "lei")},
    )
    groups, skipped = chapter_chart_groups(dataset, FACTORS_2026, CLIENT)
    assert skipped == []
    expected = (
        ("ch4.productie", "4.1", "cifrei lunare de afaceri înregistrate"),
        ("ch4.electricitate", "4.2", "consumului de energie electrică din SEN înregistrat"),
        ("ch4.gaz", "4.3", "consumului de gaz natural înregistrat"),
        ("ch4.carburant", "4.4", "consumului de carburant înregistrat"),
        ("ch4.apa", "4.5", "consumului de apă înregistrat"),
        ("ch4.apa", "4.6", "consumului de apă industrială înregistrat"),
    )
    water = iter(groups["ch4.apa"])
    for section, number, phrase in expected:
        group = next(water) if section == "ch4.apa" else groups[section][0]
        assert _captions(group.monthly) == [
            f"Fig. nr. {number} a) Evoluția lunară a {phrase} de către "
            f"{CLIENT} la nivelul anului 2025"
        ]
        assert _captions(group.annual)[0].startswith(f"Fig. nr. {number} b) ")
    assert _charts(groups["ch4.productie"][0].monthly)[0].column_axis_title == "lei/lună"


def test_every_sourced_annual_caption_and_axis_uses_the_contract() -> None:
    dataset = EnergyDataset(
        (2025,),
        {
            Carrier.electricity_grid: {
                2025: CarrierSeries({1: Reading(10, "MWh")}, Reading(10, "MWh"))
            },
            Carrier.natural_gas: {2025: CarrierSeries({1: Reading(20, "MWh")}, Reading(20, "MWh"))},
            Carrier.diesel: {2025: CarrierSeries({1: Reading(1, "t")}, Reading(1, "t"))},
            Carrier.petrol: {2025: CarrierSeries({1: Reading(2, "t")}, Reading(2, "t"))},
            Carrier.water_potable: {2025: CarrierSeries({1: Reading(3, "m³")}, Reading(3, "m³"))},
            Carrier.water_industrial: {
                2025: CarrierSeries({1: Reading(4, "m³")}, Reading(4, "m³"))
            },
        },
        {"product": {2025: CarrierSeries({1: Reading(100, "kg")}, Reading(100, "kg"))}},
        {"product": "kg"},
        {2025: Reading(1000, "lei")},
    )
    groups, skipped = chapter_chart_groups(dataset, FACTORS_2026, CLIENT)
    assert skipped == []
    expected = {
        "ch4.echiv_electric": (
            "Fig. nr. 4.7 Evoluția anuală a consumului total echivalent de energie "
            "electrică din SEN înregistrat la nivelul Atelier Exemplu SRL",
            "tep/an",
        ),
        "ch4.echiv_gaz": (
            "Fig. nr. 4.8 Evoluția anuală a consumului echivalent de gaz natural "
            "înregistrat la nivelul Atelier Exemplu SRL",
            "tep/an",
        ),
        "ch4.echiv_carburant": (
            "Fig. nr. 4.9 Evoluția anuală a consumului echivalent de carburant "
            "înregistrat la nivelul Atelier Exemplu SRL",
            "tep/an",
        ),
        "ch4.echiv_total": (
            "Fig. nr. 4.10 Evoluția anuală a consumului total echivalent de energie "
            "înregistrat la nivelul Atelier Exemplu SRL",
            "tep/an",
        ),
        "ch4.specific_electric": (
            "Fig. nr. 4.11 Evoluția anuală a consumului specific echivalent de energie "
            "electrică înregistrat la nivelul Atelier Exemplu SRL",
            "tep/t",
        ),
        "ch4.specific_gaz": (
            "Fig. nr. 4.12 Evoluția anuală a consumului specific echivalent de gaz "
            "natural înregistrat la nivelul Atelier Exemplu SRL",
            "tep/t",
        ),
        "ch4.specific_carburant": (
            "Fig. nr. 4.13 Evoluția anuală a consumului specific echivalent de "
            "carburant înregistrat la nivelul Atelier Exemplu SRL",
            "tep/t",
        ),
        "ch4.specific_total": (
            "Fig. nr. 4.14 Evoluția anuală a consumului specific echivalent total de "
            "energie înregistrat la nivelul Atelier Exemplu SRL",
            "tep/t",
        ),
        "ch4.intensitate": (
            "Fig. nr. 4.17 Tendința intensității energetice în cadrul Atelier Exemplu SRL",
            "tep/mil lei",
        ),
        "ch4.mediu": (
            "Fig. nr. 4.18 Evoluția anuală a gazelor cu efect de seră înregistrate "
            "la nivelul Atelier Exemplu SRL",
            "t CO₂/an",
        ),
    }
    for section, (caption, axis) in expected.items():
        chart = groups[section][0].annual
        assert _captions(chart) == [caption]
        assert _charts(chart)[0].column_axis_title == axis
    water = groups["ch4.specific_apa"]
    assert [_captions(group.annual)[0] for group in water] == [
        "Fig. nr. 4.15 Evoluția anuală a consumului specific de apă înregistrat "
        "la nivelul Atelier Exemplu SRL",
        "Fig. nr. 4.16 Evoluția anuală a consumului specific de apă industrială "
        "înregistrat la nivelul Atelier Exemplu SRL",
    ]
    assert [_charts(group.annual)[0].column_axis_title for group in water] == ["m³/t", "m³/t"]


def test_empty_and_zero_charts_hold_markers_and_report_no_data() -> None:
    dataset = EnergyDataset(
        (2025,),
        {Carrier.electricity_grid: {2025: CarrierSeries(annual=Reading(0, "MWh"))}},
    )
    blocks, skipped = chart_blocks("ch4.electricitate", dataset, FACTORS_2026, CLIENT)
    assert blocks == [
        Missing(
            "body",
            "Fig. nr. 4.1 a) Evoluția lunară a consumului de energie electrică "
            "din SEN înregistrat de către Atelier Exemplu SRL la nivelul anului 2025: "
            "date indisponibile",
        ),
        Missing(
            "body",
            "Fig. nr. 4.1 b) Evoluția anuală a consumului de energie electrică "
            "din SEN înregistrat la nivelul Atelier Exemplu SRL: date indisponibile",
        ),
    ]
    assert skipped == ["ch4.electricitate:2025:no_data", "ch4.electricitate:annual:no_data"]


def test_scaled_values_keep_gaps_and_source_product_name() -> None:
    dataset = replace(
        _dataset(),
        carriers={Carrier.electricity_grid: _dataset().carriers[Carrier.electricity_grid]},
        production_name={"product": "Lacuri și vopsele"},
    )
    production, _ = chart_blocks("ch4.productie", dataset, FACTORS_2026, CLIENT)
    assert _charts(production)[0].series[0].name == "Lacuri și vopsele"
    for section, metric, scale in (
        ("ch4.specific_electric", Metric("specific", (Carrier.electricity_grid,), "product"), 1000),
        ("ch4.intensitate", Metric("intensity"), 1000),
    ):
        blocks, _ = chart_blocks(section, dataset, FACTORS_2026, CLIENT)
        raw = value(dataset, FACTORS_2026, metric, 2024)[0]
        assert raw is not None
        assert _charts(blocks)[0].series[0].values[0] == raw * scale


def test_missing_figures_keep_distinct_group_numbers_and_year_letters():
    groups, _ = chapter_chart_groups(_dataset(), FACTORS_2026, CLIENT)
    skipped_year = next(
        block for block in groups["ch4.electricitate"][0].monthly if isinstance(block, Missing)
    )
    assert skipped_year.text.startswith("Fig. nr. 4.2 b) ")
    assert "la nivelul anului 2025: date indisponibile" in skipped_year.text
    missing_gas = groups["ch4.gaz"][0].annual[0]
    assert isinstance(missing_gas, Missing) and missing_gas.text.startswith("Fig. nr. 4.4 b) ")
    assert _captions(groups["ch4.carburant"][0].monthly)[0].startswith("Fig. nr. 4.5 a) ")


def test_pv_charts_use_only_held_series() -> None:
    dataset = _dataset()
    groups, skipped = chapter_chart_groups(dataset, FACTORS_2026, CLIENT)
    raw = groups["ch4.electricitate_pv"][0]
    assert any(isinstance(block, NativeChart) for block in raw.annual)
    assert all(not isinstance(block, NativeChart) for block in raw.monthly)
    assert "ch4.electricitate_pv:2024:no_data" in skipped
    assert groups["ch4.echiv_pv"]
    assert groups["ch4.specific_pv"]
