"""Ch. 4 commentary in her words: the intro, figure and table lead-ins, trend comments, annual
lists and the variable-factor lists (#162). Everything but the factor bullets is deterministic."""

from __future__ import annotations

from collections.abc import Sequence

from ema.consumption_analysis.analysis import Metric, value
from ema.core.office.blocks import (
    Block,
    BulletList,
    Missing,
    NativeChart,
    Num,
    Paragraph,
    Ref,
    Segment,
)
from ema.core.office.chart_series import Series
from ema.core.office.missing_text import MISSING_TEXT
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset

INTRO_CLIENT = (
    "În capitolele anterioare au fost descriși consumatorii energetici existenți în cadrul "
    "conturului energetic în care reprezentanții ",
    " își desfășoară activitatea.",
)
INTRO_PERIOD = (
    "Analiza cantitativă a consumurilor energetice din cadrul platformei se bazează pe datele "
    "înregistrate în perioada {first} – {last}."
)
# Under 3 % of the mean, first to last fitted point, the series reads as flat (#162 D2).
TREND_BAND = 0.03
GROWTH = "de creștere"
DECLINE = "de scădere"
FLAT = "relativ constantă"
TABLE_OPENING = "În tabelul numărul "
ANNUAL_OPENING = "În ceea ce privește consumurile anuale de "
ANNUAL_LEAD = (
    ANNUAL_OPENING + "{resource} înregistrate de către societate în perioada de analiză, se "
    "desprind următoarele:"
)
# Her wording where it differs from the carrier's plain name.
RESOURCE = {
    **CARRIER_NAMES_RO,
    Carrier.electricity_pv: "energie electrică din parcul fotovoltaic propriu",
    Carrier.natural_gas: "gaz natural",
}
FACTOR_PREFIX = "narrative.ch4.factors."
FACTOR_TAIL = (
    " ține cont de următorii factori variabili relevanți în ceea ce privește indicatorii "
    "energetici ai societății:"
)
FACTOR_LEAD = {
    "ch4.electricitate": "Curba de consum a energiei electrice" + FACTOR_TAIL,
    "ch4.electricitate_pv": (
        "Curba de producție a energiei electrice din parcul fotovoltaic" + FACTOR_TAIL
    ),
    "ch4.gaz": "Curba de consum a gazului natural" + FACTOR_TAIL,
    "ch4.carburant": "Curba de consum a carburantului" + FACTOR_TAIL,
    "ch4.apa": "Curba de consum a apei" + FACTOR_TAIL,
}


def intro(dataset: EnergyDataset, client: str) -> list[Block]:
    years = dataset.years
    return [
        Paragraph("body", [INTRO_CLIENT[0], client or Num(None, 0), INTRO_CLIENT[1]]),
        Paragraph("body", [INTRO_PERIOD.format(first=years[0], last=years[-1])]),
    ]


def trend(values: Sequence[float | None]) -> str | None:
    """The least-squares line's change from its first to its last fitted point, relative to the
    series mean; none under two points."""
    points = [(float(x), y) for x, y in enumerate(values) if y is not None]
    if len(points) < 2:
        return None
    count = len(points)
    mean_x = sum(x for x, _ in points) / count
    mean_y = sum(y for _, y in points) / count
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / sum(
        (x - mean_x) ** 2 for x, _ in points
    )
    change = slope * (points[-1][0] - points[0][0])
    # A series around zero, as [-10, 0, 10], is measured against its mean absolute value.
    scale = abs(mean_y) or sum(abs(y) for _, y in points) / count
    if scale == 0 or abs(change) < TREND_BAND * scale:
        return FLAT
    return GROWTH if change > 0 else DECLINE


def figure_lead(number: str, period: str, subject: str) -> Paragraph:
    return Paragraph(
        "body", [f"În figura numărul {number} se prezintă evoluția {period} a {subject}."]
    )


def figure_trend(number: str, word: str, subject: str) -> Paragraph:
    return Paragraph(
        "body", [f"Conform figurii numărul {number} se observă tendința {word} a {subject}."]
    )


def _totals(series: list[Series]) -> list[float | None]:
    """The chart's points summed across its series, as the trend reads them."""
    return [
        None if None in points else sum(point for point in points if point is not None)
        for points in zip(*(item.values for item in series), strict=True)
    ]


def figure_blocks(
    chart: NativeChart, number: str, caption: str, when: str, subject: str
) -> list[Block]:
    """Her lead-in, the chart and its caption, then the trend she reads from it."""
    word = trend(_totals(chart.series))
    return [
        figure_lead(number, when, subject),
        chart,
        Paragraph("chart_caption", [caption, "", "", ""]),
        *([figure_trend(number, word, subject)] if word else []),
    ]


def period(years: Sequence[int]) -> str:
    return f"în anul {years[0]}" if len(years) == 1 else f"în perioada {years[0]} – {years[-1]}"


def table_lead(caption_id: str, subject: str) -> Paragraph:
    return Paragraph("body", [TABLE_OPENING, Ref("tab", caption_id), f" se prezintă {subject}."])


def annual_list(
    dataset: EnergyDataset,
    factors: FactorTable,
    carrier: Carrier,
    years: tuple[int, ...],
    unit: str,
) -> list[Block]:
    """Her lead-in and one bullet per year, each the value the chapter's totals print."""
    items: list[list[Segment]] = []
    for index, year in enumerate(years):
        number, fact = value(dataset, factors, Metric("carrier", (carrier,)), year, filed=False)
        items.append(
            [
                f"pentru anul {year} s-au înregistrat ",
                Num(number, 2, f"{unit}/an", fact),
                "." if index == len(years) - 1 else ",",
            ]
        )
    return [
        Paragraph("body", [ANNUAL_LEAD.format(resource=RESOURCE[carrier])]),
        BulletList("bullet", items),
    ]


def factor_key(section: str) -> str:
    """`ch4.gaz` drafts into `narrative.ch4.factors.gaz`."""
    return FACTOR_PREFIX + section.removeprefix("ch4.")


def factor_bullets(text: str | None) -> list[str]:
    """The drafted list, one factor per line, punctuated like her lists: ';' then '.'."""
    lines = [
        line.strip().lstrip("-•–").strip().rstrip(";,.").strip()
        for line in (text or "").splitlines()
    ]
    lines = [line for line in lines if line]
    return [line + ("." if i == len(lines) - 1 else ";") for i, line in enumerate(lines)]


def factor_blocks(section: str, text: str | None) -> list[Block]:
    """The lead-in, then the drafted factors, or the missing marker without a draft."""
    bullets = factor_bullets(text)
    return [
        Paragraph("body", [FACTOR_LEAD[section]]),
        BulletList("bullet", [[bullet] for bullet in bullets])
        if bullets
        else Missing("body", MISSING_TEXT),
    ]
