"""Ch. 4 commentary like her audits (#162): intro, figure and table comments, annual lists, the
monthly table shape and the variable-factor section, each sentence copied from the plan."""

from __future__ import annotations

import pytest

from ema.audit.chapter_four_blocks import chapter_four_blocks
from ema.audit.chapter_four_chart_placement import place_chart_groups
from ema.audit.chapter_four_charts import chapter_chart_groups
from ema.audit.chapter_four_comments import FACTOR_LEAD, trend
from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.blocks import (
    Block,
    BulletList,
    Caption,
    Missing,
    NativeChart,
    Num,
    Paragraph,
    Ref,
    Table,
)
from ema.core.office.missing_text import MISSING_TEXT
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading

CLIENT = "Atelier Exemplu SRL"
YEARS = (2023, 2024, 2025)


def _months(start: float, step: float, unit: str) -> CarrierSeries:
    months = {month: Reading(start + step * (month - 1), unit) for month in range(1, 13)}
    total = sum(float(reading.value or 0) for reading in months.values())
    return CarrierSeries(months, Reading(total, unit))


def _dataset() -> EnergyDataset:
    return EnergyDataset(
        YEARS,
        {
            Carrier.electricity_grid: {
                year: _months(100 + 10 * index, 1, "MWh") for index, year in enumerate(YEARS)
            },
            Carrier.natural_gas: {year: _months(50, -1, "MWh") for year in YEARS},
            Carrier.diesel: {year: _months(2, 0, "t") for year in YEARS},
            Carrier.petrol: {year: _months(1, 0, "t") for year in YEARS},
            Carrier.water_potable: {year: _months(30, 0, "m³") for year in YEARS},
        },
    )


def _section(blocks: list[Block], section: str) -> list[Block]:
    start = next(
        i
        for i, b in enumerate(blocks)
        if isinstance(b, Paragraph) and b.proto == "heading:" + section
    )
    end = next(
        (
            i
            for i in range(start + 1, len(blocks))
            if isinstance(blocks[i], Paragraph) and blocks[i].proto.startswith("heading:")
        ),
        len(blocks),
    )
    return blocks[start + 1 : end]


def _text(block: Block) -> str:
    if not isinstance(block, Paragraph):
        return ""
    return "".join(segment for segment in block.segments if isinstance(segment, str))


def test_the_intro_opens_the_chapter_before_its_first_section() -> None:
    blocks = chapter_four_blocks(_dataset(), FACTORS_2026, client=CLIENT)
    assert blocks[:2] == [
        Paragraph(
            "body",
            [
                "În capitolele anterioare au fost descriși consumatorii energetici existenți în "
                "cadrul conturului energetic în care reprezentanții ",
                CLIENT,
                " își desfășoară activitatea.",
            ],
        ),
        Paragraph(
            "body",
            [
                "Analiza cantitativă a consumurilor energetice din cadrul platformei se bazează "
                "pe datele înregistrate în perioada 2023 – 2025."
            ],
        ),
    ]
    assert isinstance(blocks[2], Paragraph) and blocks[2].proto.startswith("heading:ch4.")


def test_the_intro_without_a_client_name_marks_it_missing() -> None:
    first = chapter_four_blocks(_dataset(), FACTORS_2026)[0]
    assert isinstance(first, Paragraph) and first.segments[1] == Num(None, 0)


def _linear(change: float, points: int = 2) -> list[float | None]:
    """A straight series around 100 whose first-to-last change is `change` % of its mean."""
    return [100 + change * (index / (points - 1) - 0.5) for index in range(points)]


@pytest.mark.parametrize(
    ("change", "word"),
    [
        (2.9, "relativ constantă"),
        (3.1, "de creștere"),
        (-3.1, "de scădere"),
        (-2.9, "relativ constantă"),
        (0.0, "relativ constantă"),
    ],
)
def test_trend_reads_the_least_squares_change_against_a_three_percent_band(
    change: float, word: str
) -> None:
    assert trend(_linear(change)) == word
    assert trend(_linear(change, 12)) == word


@pytest.mark.parametrize(
    ("values", "word"),
    [
        ([0, 0, 0], "relativ constantă"),
        # Mean zero, slope not: measured against the mean absolute value.
        ([-10, 0, 10], "de creștere"),
        ([10, 0, -10], "de scădere"),
        ([-1, 0, 0, 1.02], "de creștere"),
        # Negative means: the sign of the fitted change, its size against |mean|.
        ([-110, -100], "de creștere"),
        ([-100, -110], "de scădere"),
        ([-101.45, -98.55], "relativ constantă"),
    ],
)
def test_trend_around_zero_and_below_it(values: list[float | None], word: str) -> None:
    assert trend(values) == word


def test_trend_fits_noisy_and_gappy_series_and_needs_two_points() -> None:
    # Noise around a level line: the fit changes by under 1 % of the mean.
    assert trend([98, 104, 99, 105, 97]) == "relativ constantă"
    assert trend([90, None, 95, 100, None, 110]) == "de creștere"
    assert trend([0, 0, 0]) == "relativ constantă"
    assert trend([5, None]) is None
    assert trend([]) is None


def test_every_bar_figure_has_her_lead_in_and_trend_comment() -> None:
    groups, _ = chapter_chart_groups(_dataset(), FACTORS_2026, CLIENT)
    gas = groups["ch4.gaz"][0]
    lead, chart, caption, comment = gas.monthly[:4]
    number = _text(caption).split()[2] + " a)"
    assert isinstance(chart, NativeChart)
    assert _text(lead) == (
        f"În figura numărul {number} se prezintă evoluția lunară a consumului de gaz natural "
        f"înregistrat de către {CLIENT} la nivelul anului 2023."
    )
    assert _text(comment) == (
        f"Conform figurii numărul {number} se observă tendința de scădere a consumului de gaz "
        f"natural înregistrat de către {CLIENT} la nivelul anului 2023."
    )
    lead, chart, caption, comment = gas.annual
    annual = _text(caption).split()[2] + " d)"
    assert _text(caption).startswith(f"Fig. nr. {annual} ")
    assert _text(lead) == (
        f"În figura numărul {annual} se prezintă evoluția anuală a consumului de gaz natural "
        f"înregistrat la nivelul {CLIENT}."
    )
    assert _text(comment) == (
        f"Conform figurii numărul {annual} se observă tendința relativ constantă a consumului de "
        f"gaz natural înregistrat la nivelul {CLIENT}."
    )
    electric = groups["ch4.electricitate"][0].annual
    assert _text(electric[-1]).startswith("Conform figurii numărul 4.")
    assert "tendința de creștere a consumului de energie electrică din SEN" in _text(electric[-1])
    for section, items in groups.items():
        for group in items:
            if group.pies:
                continue
            for blocks in (group.monthly, group.annual):
                charts = [i for i, b in enumerate(blocks) if isinstance(b, NativeChart)]
                for at in charts:
                    assert _text(blocks[at - 1]).startswith("În figura numărul 4."), section
                    assert _text(blocks[at + 2]).startswith("Conform figurii numărul 4."), section


def test_a_table_is_led_in_by_its_number() -> None:
    gas = _section(chapter_four_blocks(_dataset(), FACTORS_2026), "ch4.gaz")
    lead = gas[1]
    caption = gas[2]
    assert isinstance(caption, Caption)
    assert lead == Paragraph(
        "body",
        [
            "În tabelul numărul ",
            Ref("tab", caption.id),
            " se prezintă evoluția lunară a consumului de gaz natural în perioada 2023 – 2025.",
        ],
    )
    blocks = chapter_four_blocks(_dataset(), FACTORS_2026)
    captions = [b for b in blocks if isinstance(b, Caption)]
    leads = [
        b
        for b in blocks
        if isinstance(b, Paragraph) and b.segments and b.segments[0] == "În tabelul numărul "
    ]
    assert [lead.segments[1] for lead in leads] == [Ref("tab", c.id) for c in captions]


def test_monthly_tables_are_two_per_resource_with_a_row_per_year() -> None:
    blocks = chapter_four_blocks(_dataset(), FACTORS_2026)
    for section, carriers in (
        ("ch4.electricitate", 1),
        ("ch4.gaz", 1),
        ("ch4.carburant", 2),
        ("ch4.apa", 1),
        ("ch4.echiv_total", 1),
    ):
        body = _section(blocks, section)
        tables = [b for b in body if isinstance(b, Table)]
        assert [t.proto for t in tables] == ["months_first", "months_second"] * carriers, section
        assert sum(isinstance(b, Caption) for b in body) == carriers, section
        for table in tables:
            assert [row[0] for row in table.rows] == [[str(year)] for year in YEARS], section


@pytest.mark.parametrize(
    ("section", "carrier", "resource", "unit"),
    [
        ("ch4.electricitate", Carrier.electricity_grid, "energie electrică din SEN", "MWh"),
        ("ch4.gaz", Carrier.natural_gas, "gaz natural", "MWh"),
        ("ch4.carburant", Carrier.diesel, "motorină", "t"),
        ("ch4.carburant", Carrier.petrol, "benzină", "t"),
        ("ch4.apa", Carrier.water_potable, "apă potabilă", "m³"),
    ],
)
def test_the_annual_list_prints_the_chapter_totals(
    section: str, carrier: Carrier, resource: str, unit: str
) -> None:
    dataset = _dataset()
    body = _section(chapter_four_blocks(dataset, FACTORS_2026), section)
    lead = Paragraph(
        "body",
        [
            f"În ceea ce privește consumurile anuale de {resource} înregistrate de către "
            "societate în perioada de analiză, se desprind următoarele:"
        ],
    )
    bullets = body[body.index(lead) + 1]
    assert isinstance(bullets, BulletList) and bullets.proto == "bullet"
    totals = [
        value(dataset, FACTORS_2026, Metric("carrier", (carrier,)), y, filed=False) for y in YEARS
    ]
    assert bullets.items == [
        [
            f"pentru anul {year} s-au înregistrat ",
            Num(number, 2, f"{unit}/an", fact),
            "." if year == YEARS[-1] else ",",
        ]
        for year, (number, fact) in zip(YEARS, totals, strict=True)
    ]
    # The same totals the annual figure draws.
    groups, _ = chapter_chart_groups(dataset, FACTORS_2026, CLIENT)
    drawn = [
        series.values
        for group in groups[section]
        for block in group.annual
        if isinstance(block, NativeChart)
        for series in block.series
        if series.name.endswith(resource) or section != "ch4.carburant"
    ]
    assert [number for number, _ in totals] in drawn
    assert not any(_text(b).startswith("Total anual") for b in body if isinstance(b, Paragraph))


def test_the_annual_chart_sits_between_the_tables_and_the_annual_list() -> None:
    dataset = _dataset()
    groups, _ = chapter_chart_groups(dataset, FACTORS_2026, CLIENT)
    blocks = place_chart_groups(chapter_four_blocks(dataset, FACTORS_2026, client=CLIENT), groups)
    gas = _section(blocks, "ch4.gaz")
    kinds = [
        "chart"
        if isinstance(b, NativeChart)
        else "table"
        if isinstance(b, Table)
        else "list"
        if isinstance(b, BulletList | Missing)
        else _text(b)[:12]
        for b in gas
    ]
    last_table = max(i for i, kind in enumerate(kinds) if kind == "table")
    annual_chart = max(i for i, kind in enumerate(kinds) if kind == "chart")
    listed = next(i for i, b in enumerate(gas) if _text(b).startswith("În ceea ce privește"))
    factors = gas.index(Paragraph("body", [FACTOR_LEAD["ch4.gaz"]]))
    assert last_table < annual_chart < listed < factors
    assert kinds[annual_chart - 1] == "În figura nu" and kinds[annual_chart + 2] == "Conform figu"


def test_the_factor_lead_ins_are_hers_verbatim() -> None:
    assert FACTOR_LEAD == {
        "ch4.electricitate": (
            "Curba de consum a energiei electrice ține cont de următorii factori variabili "
            "relevanți în ceea ce privește indicatorii energetici ai societății:"
        ),
        "ch4.electricitate_pv": (
            "Curba de producție a energiei electrice din parcul fotovoltaic ține cont de "
            "următorii factori variabili relevanți în ceea ce privește indicatorii energetici "
            "ai societății:"
        ),
        "ch4.gaz": (
            "Curba de consum a gazului natural ține cont de următorii factori variabili "
            "relevanți în ceea ce privește indicatorii energetici ai societății:"
        ),
        "ch4.carburant": (
            "Curba de consum a carburantului ține cont de următorii factori variabili "
            "relevanți în ceea ce privește indicatorii energetici ai societății:"
        ),
        "ch4.apa": (
            "Curba de consum a apei ține cont de următorii factori variabili relevanți în ceea "
            "ce privește indicatorii energetici ai societății:"
        ),
    }


def test_a_drafted_factor_list_follows_the_annual_list_punctuated_like_hers() -> None:
    texts = {"ch4.factors.gaz": "regimul de lucru: schimburile active\n- sezonul rece;\n\n"}
    gas = _section(chapter_four_blocks(_dataset(), FACTORS_2026, texts=texts), "ch4.gaz")
    lead = Paragraph("body", [FACTOR_LEAD["ch4.gaz"]])
    assert gas[gas.index(lead) + 1] == BulletList(
        "bullet", [["regimul de lucru: schimburile active;"], ["sezonul rece."]]
    )


def test_a_resource_without_a_draft_gets_the_lead_in_and_the_marker() -> None:
    blocks = chapter_four_blocks(_dataset(), FACTORS_2026)
    for section in ("ch4.electricitate", "ch4.gaz", "ch4.carburant", "ch4.apa"):
        body = _section(blocks, section)
        lead = Paragraph("body", [FACTOR_LEAD[section]])
        assert body[body.index(lead) + 1] == Missing("body", MISSING_TEXT), section
    # Equivalent sections keep their totals and have no factor list.
    equivalent = _section(blocks, "ch4.echiv_gaz")
    assert not any(isinstance(b, Paragraph) and _text(b).startswith("Curba") for b in equivalent)
    assert any(isinstance(b, Paragraph) and _text(b).startswith("Total anual") for b in equivalent)
