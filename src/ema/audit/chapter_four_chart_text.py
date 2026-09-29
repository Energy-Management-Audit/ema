"""Verbatim caption templates for the supported chapter-four charts."""

import re

from ema.consumption_analysis.metric_kind import MetricKind
from ema.energy_data.carriers import Carrier


def is_turnover_unit(unit: str) -> bool:
    return re.search(r"\blei\b", unit, re.IGNORECASE) is not None


def scaled_unit(unit: str, kind: MetricKind) -> tuple[str, float]:
    """Scale display denominators; domain values retain their source units."""
    if kind not in {"specific", "water_specific", "intensity"}:
        return unit, 1.0
    numerator, separator, denominator = unit.partition("/")
    if separator and (denominator == "kg" or denominator.startswith("kg ")):
        return numerator + "/t" + denominator[2:], 1000.0
    if separator and denominator == "lei":
        return numerator + "/mil lei", 1_000_000.0
    if separator and denominator == "1000 lei":
        return numerator + "/mil lei", 1000.0
    return unit, 1.0


MONTHS = (
    "Ianuarie",
    "Februarie",
    "Martie",
    "Aprilie",
    "Mai",
    "Iunie",
    "Iulie",
    "August",
    "Septembrie",
    "Octombrie",
    "Noiembrie",
    "Decembrie",
)
STYLE_PART = "__chapter_four_chart_style__"
SUBJECT = {
    Carrier.electricity_grid: "consumului de energie electrică din SEN",
    Carrier.natural_gas: "consumului de gaz natural",
    Carrier.water_potable: "consumului de apă",
    Carrier.water_industrial: "consumului de apă industrială",
}
ANNUAL = {
    "ch4.echiv_electric": (
        "Evoluția anuală a consumului total echivalent de energie electrică "
        "din SEN înregistrat la nivelul {client}"
    ),
    "ch4.echiv_gaz": (
        "Evoluția anuală a consumului echivalent de gaz natural înregistrat la nivelul {client}"
    ),
    "ch4.echiv_carburant": (
        "Evoluția anuală a consumului echivalent de carburant înregistrat la nivelul {client}"
    ),
    "ch4.echiv_total": (
        "Evoluția anuală a consumului total echivalent de energie înregistrat la nivelul {client}"
    ),
    "ch4.specific_electric": (
        "Evoluția anuală a consumului specific echivalent de energie electrică "
        "înregistrat la nivelul {client}"
    ),
    "ch4.specific_gaz": (
        "Evoluția anuală a consumului specific echivalent de gaz natural "
        "înregistrat la nivelul {client}"
    ),
    "ch4.specific_carburant": (
        "Evoluția anuală a consumului specific echivalent de carburant "
        "înregistrat la nivelul {client}"
    ),
    "ch4.specific_total": (
        "Evoluția anuală a consumului specific echivalent total de energie "
        "înregistrat la nivelul {client}"
    ),
    "ch4.intensitate": "Tendința intensității energetice în cadrul {client}",
    "ch4.mediu": "Evoluția anuală a gazelor cu efect de seră înregistrate la nivelul {client}",
}
WATER_ANNUAL = {
    Carrier.water_potable: (
        "Evoluția anuală a consumului specific de apă înregistrat la nivelul {client}"
    ),
    Carrier.water_industrial: (
        "Evoluția anuală a consumului specific de apă industrială înregistrat la nivelul {client}"
    ),
}
