"""Ch. 4 share pies: slices, fractions, captions, lead-ins, gaps and placement."""

from dataclasses import replace

import pytest

from ema.audit.chapter_four_blocks import chapter_four_blocks
from ema.audit.chapter_four_chart_placement import place_chart_groups
from ema.audit.chapter_four_charts import chapter_chart_groups
from ema.audit.chapter_four_pies import mix_pies, pv_pies
from ema.audit.chapter_four_sentences import sentence_plan
from ema.core.office.blocks import Block, Missing, NativeChart, Paragraph
from ema.energy_data.calc import tep
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026, Factor
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading

CLIENT = "Atelier Exemplu SRL"
MIX = (
    "Ponderea diverselor surse de energie în total consum înregistrat în cadrul "
    f"{CLIENT} la nivelul anului "
)
PV = (
    "Ponderea energiei electrice consumată din parcul fotovoltaic propriu din total energie "
    "electrică la nivelul anului "
)
MIX_PLURAL = (
    "În ceea ce privește ponderile diverselor resurse energetice în total consum energetic "
    "înregistrat de către societate în perioada de analiză, în figurile cu numărul 4.{k} sunt "
    "prezentate aceste informații."
)
MIX_SINGULAR = (
    "În ceea ce privește ponderile diverselor resurse energetice în total consum energetic "
    "înregistrat de către societate în perioada de analiză, în figura numărul 4.{k} sunt "
    "prezentate aceste informații."
)
PV_PLURAL = (
    "În figurile cu numărul 4.{k} se prezintă ponderea energiei electrice consumată din parcul "
    "fotovoltaic propriu din total energie electrică consumată în perioada de analiză la "
    "nivelul societății."
)
PV_SINGULAR = (
    "În figura numărul 4.{k} se prezintă ponderea energiei electrice consumată din parcul "
    "fotovoltaic propriu din total energie electrică consumată în perioada de analiză la "
    "nivelul societății."
)
MIX_LABELS = ["Energie electrică din SEN", "Energie electrică fotovoltaică", "Gaze naturale"]
PV_LABELS = [
    "Energia electrică achiziționată din SEN",
    "Energia electrică consumată din sistemul fotovoltaic propriu",
]


def _annual(values: dict[int, float | None], unit: str) -> dict[int, CarrierSeries]:
    return {year: CarrierSeries(annual=Reading(value, unit)) for year, value in values.items()}


def _dataset() -> EnergyDataset:
    return EnergyDataset(
        (2024, 2025),
        {
            Carrier.electricity_grid: _annual({2024: 100, 2025: 200}, "MWh"),
            Carrier.electricity_pv: _annual({2024: 50, 2025: 40}, "MWh"),
            Carrier.natural_gas: _annual({2024: 300, 2025: 100}, "MWh"),
            Carrier.diesel: _annual({2024: 1, 2025: 2}, "t"),
            Carrier.petrol: _annual({2024: 2, 2025: 1}, "t"),
        },
    )


def _texts(blocks: list[Block]) -> list[str]:
    return [
        str(block.segments[0]) if isinstance(block, Paragraph) else block.text
        for block in blocks
        if isinstance(block, Paragraph | Missing)
    ]


def _pies(blocks: list[Block]) -> list[NativeChart]:
    return [block for block in blocks if isinstance(block, NativeChart)]


def test_mix_pies_sum_fuels_into_carburant_and_continue_the_section_numbering() -> None:
    dataset = _dataset()
    groups, skipped = chapter_chart_groups(dataset, FACTORS_2026, CLIENT)
    annual, pies = groups["ch4.echiv_total"]
    number = int(_texts(annual.annual)[0].split()[2].removeprefix("4."))
    assert (pies.label, pies.monthly) == (None, [])
    assert _texts(pies.annual) == [
        MIX_PLURAL.format(k=number + 1),
        f"Fig. nr. 4.{number + 1} a) {MIX}2024",
        f"Fig. nr. 4.{number + 1} b) {MIX}2025",
    ]
    assert all(block.proto == "chart_caption" for block in pies.annual[2::2])
    for chart, year in zip(_pies(pies.annual), dataset.years, strict=True):
        assert (chart.proto, chart.pie, len(chart.series)) == ("chart", "mix", 1)
        [series] = chart.series
        assert (series.name, series.categories) == ("Pondere", [*MIX_LABELS, "Carburant"])
        parts = [
            tep(dataset, FACTORS_2026, carrier, year).value or 0.0
            for carrier in (Carrier.electricity_grid, Carrier.electricity_pv, Carrier.natural_gas)
        ]
        fuel = sum(
            tep(dataset, FACTORS_2026, carrier, year).value or 0.0
            for carrier in (Carrier.diesel, Carrier.petrol)
        )
        total = sum(parts) + fuel
        assert series.values == pytest.approx([*(part / total for part in parts), fuel / total])
    assert not [note for note in skipped if ":pie:" in note]
    following = groups["ch4.intensitate"][0].annual
    assert _texts(following)[0].startswith(f"Fig. nr. 4.{number + 2} ")


def test_other_carriers_follow_in_carrier_order_and_water_and_cogeneration_stay_out() -> None:
    factors = replace(
        FACTORS_2026,
        tep=(
            *FACTORS_2026.tep,
            Factor(Carrier.coal, "t", 0.5, "test"),
            Factor(Carrier.purchased_heat, "Gcal", 0.1, "test"),
            Factor(Carrier.electricity_cogen, "MWh", 0.086, "test"),
        ),
    )
    dataset = EnergyDataset(
        (2025,),
        {
            Carrier.purchased_heat: _annual({2025: 10}, "Gcal"),
            Carrier.coal: _annual({2025: 2}, "t"),
            Carrier.electricity_grid: _annual({2025: 100}, "MWh"),
            Carrier.electricity_cogen: _annual({2025: 100}, "MWh"),
            Carrier.water_potable: _annual({2025: 5}, "m³"),
        },
    )
    [chart] = _pies(mix_pies(dataset, factors, CLIENT, 3, []))
    assert chart.series[0].categories == [
        "Energie electrică din SEN",
        "Cărbune",
        "Energie termică achiziționată",
    ]
    assert chart.series[0].values == pytest.approx([8.6 / 10.6, 1 / 10.6, 1 / 10.6])


def test_a_single_carrier_year_gives_no_pie_marker_or_letter() -> None:
    dataset = EnergyDataset((2025,), {Carrier.electricity_grid: _annual({2025: 10}, "MWh")})
    skipped: list[str] = []
    assert mix_pies(dataset, FACTORS_2026, CLIENT, 7, skipped) == []
    assert skipped == ["ch4.echiv_total:pie:2025:single_carrier"]
    two_years = EnergyDataset(
        (2024, 2025),
        {
            Carrier.electricity_grid: _annual({2024: 10, 2025: 10}, "MWh"),
            Carrier.natural_gas: _annual({2025: 30}, "MWh"),
        },
    )
    skipped = []
    blocks = mix_pies(two_years, FACTORS_2026, CLIENT, 7, skipped)
    assert _texts(blocks) == [MIX_SINGULAR.format(k=7), f"Fig. nr. 4.7 {MIX}2025"]
    assert _pies(blocks)[0].series[0].values == pytest.approx([0.25, 0.75])
    assert skipped == ["ch4.echiv_total:pie:2024:single_carrier"]


def test_one_year_has_the_singular_lead_in_and_no_letter() -> None:
    dataset = EnergyDataset(
        (2025,),
        {
            Carrier.electricity_grid: _annual({2025: 10}, "MWh"),
            Carrier.natural_gas: _annual({2025: 30}, "MWh"),
        },
    )
    blocks = mix_pies(dataset, FACTORS_2026, CLIENT, 7, [])
    assert _texts(blocks) == [MIX_SINGULAR.format(k=7), f"Fig. nr. 4.7 {MIX}2025"]
    assert _pies(blocks)[0].series[0].categories == ["Energie electrică din SEN", "Gaze naturale"]


@pytest.mark.parametrize(
    ("gas", "unit", "reason"),
    [
        (None, "MWh", "no_data"),  # a gap in the reading
        (30, "Nm³", "no_data"),  # no tep factor for the unit
    ],
)
def test_a_carrier_without_tep_makes_the_year_missing(
    gas: float | None, unit: str, reason: str
) -> None:
    dataset = EnergyDataset(
        (2024, 2025),
        {
            Carrier.electricity_grid: _annual({2024: 10, 2025: 10}, "MWh"),
            Carrier.natural_gas: {
                2024: CarrierSeries(annual=Reading(30, "MWh")),
                2025: CarrierSeries(annual=Reading(gas, unit)),
            },
        },
    )
    skipped: list[str] = []
    blocks = mix_pies(dataset, FACTORS_2026, CLIENT, 5, skipped)
    assert _texts(blocks) == [
        MIX_PLURAL.format(k=5),
        f"Fig. nr. 4.5 a) {MIX}2024",
        f"Fig. nr. 4.5 b) {MIX}2025: date indisponibile",
    ]
    assert isinstance(blocks[-1], Missing)
    assert skipped == [f"ch4.echiv_total:pie:2025:{reason}"]


def test_zero_total_and_nine_slices_are_missing() -> None:
    others = (Carrier.coal, Carrier.coke, Carrier.wood, Carrier.biomass, Carrier.biogas)
    factors = replace(
        FACTORS_2026,
        tep=(*FACTORS_2026.tep, *(Factor(carrier, "t", 1.0, "test") for carrier in others)),
    )
    carriers = {
        Carrier.electricity_grid: _annual({2024: 0, 2025: 10}, "MWh"),
        Carrier.natural_gas: _annual({2024: 0, 2025: 10}, "MWh"),
        Carrier.electricity_pv: _annual({2025: 10}, "MWh"),
        Carrier.diesel: _annual({2025: 1}, "t"),
        **{carrier: _annual({2025: 1}, "t") for carrier in others},
    }
    skipped: list[str] = []
    blocks = mix_pies(EnergyDataset((2024, 2025), carriers), factors, CLIENT, 9, skipped)
    assert _texts(blocks) == [
        MIX_PLURAL.format(k=9),
        f"Fig. nr. 4.9 a) {MIX}2024: date indisponibile",
        f"Fig. nr. 4.9 b) {MIX}2025: date indisponibile",
    ]
    assert _pies(blocks) == []
    assert skipped == [
        "ch4.echiv_total:pie:2024:no_data",
        "ch4.echiv_total:pie:2025:too_many_slices",
    ]


def test_pv_pies_share_grid_and_pv_per_pv_year() -> None:
    skipped: list[str] = []
    blocks = pv_pies(_dataset(), FACTORS_2026, CLIENT, 4, skipped)
    assert _texts(blocks) == [
        PV_PLURAL.format(k=4),
        f"Fig. nr. 4.4 a) {PV}2024",
        f"Fig. nr. 4.4 b) {PV}2025",
    ]
    first, second = _pies(blocks)
    assert (first.pie, first.series[0].name, first.series[0].categories) == (
        "pv",
        "Pondere",
        PV_LABELS,
    )
    assert first.series[0].values == pytest.approx([100 / 150, 50 / 150])
    assert second.series[0].values == pytest.approx([200 / 240, 40 / 240])
    assert skipped == []


def test_pv_pies_cover_only_pv_years_and_mark_a_missing_grid_annual() -> None:
    dataset = EnergyDataset(
        (2023, 2024, 2025),
        {
            Carrier.electricity_grid: _annual({2023: 90, 2024: 100, 2025: 80}, "MWh"),
            Carrier.electricity_pv: _annual({2025: 20}, "MWh"),
        },
    )
    blocks = pv_pies(dataset, FACTORS_2026, CLIENT, 2, [])
    assert _texts(blocks) == [PV_SINGULAR.format(k=2), f"Fig. nr. 4.2 {PV}2025"]
    assert _pies(blocks)[0].series[0].values == pytest.approx([0.8, 0.2])
    gap = replace(
        dataset,
        carriers={
            Carrier.electricity_grid: {2025: CarrierSeries({1: Reading(None, "MWh")})},
            Carrier.electricity_pv: _annual({2024: 10, 2025: 20}, "MWh"),
        },
    )
    skipped: list[str] = []
    blocks = pv_pies(gap, FACTORS_2026, CLIENT, 2, skipped)
    assert _texts(blocks) == [
        PV_PLURAL.format(k=2),
        f"Fig. nr. 4.2 a) {PV}2024: date indisponibile",
        f"Fig. nr. 4.2 b) {PV}2025: date indisponibile",
    ]
    assert skipped == [
        "ch4.electricitate_pv:pie:2024:no_data",
        "ch4.electricitate_pv:pie:2025:no_data",
    ]


def test_a_dataset_without_pv_has_no_pv_pies_or_notes() -> None:
    carriers = dict(_dataset().carriers)
    del carriers[Carrier.electricity_pv]
    dataset = EnergyDataset((2024, 2025), carriers)
    skipped: list[str] = []
    assert pv_pies(dataset, FACTORS_2026, CLIENT, 1, skipped) == []
    groups, notes = chapter_chart_groups(dataset, FACTORS_2026, CLIENT)
    assert "ch4.electricitate_pv" not in groups
    assert skipped == [] and not [note for note in notes if "electricitate_pv" in note]


@pytest.mark.parametrize(
    ("section", "annual"),
    [
        ("ch4.echiv_total", "Evoluția anuală a consumului total echivalent de energie"),
        ("ch4.electricitate_pv", "Evoluția anuală a consumului de energie electrică fotovolt"),
    ],
)
def test_pies_follow_the_annual_chart_and_precede_the_section_sentences(
    section: str, annual: str
) -> None:
    dataset = _dataset()
    groups, _ = chapter_chart_groups(dataset, FACTORS_2026, CLIENT)
    blocks = place_chart_groups(chapter_four_blocks(dataset, FACTORS_2026, client=CLIENT), groups)
    start = blocks.index(next(b for b in blocks if getattr(b, "proto", "") == "heading:" + section))
    end = next(
        (
            i
            for i in range(start + 1, len(blocks))
            if getattr(blocks[i], "proto", "").startswith("heading:")
        ),
        len(blocks),
    )
    body = blocks[start + 1 : end]
    pies = groups[section][-1].annual
    at = next(i for i, block in enumerate(body) if block is pies[0])
    assert body[at : at + len(pies)] == pies
    caption = body[at - 1]
    assert isinstance(caption, Paragraph) and caption.proto == "chart_caption"
    assert annual in str(caption.segments[0])
    sentences = sentence_plan(dataset, FACTORS_2026).sections.get(section, [])
    assert body[at + len(pies) :] == sentences
    if section == "ch4.echiv_total":
        assert sentences
