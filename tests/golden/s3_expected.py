"""Reviewed exception contracts for the reference workbooks; no client values."""

from __future__ import annotations

from typing import Literal, NamedTuple

CellKey = tuple[str, str, str, int, int | None]


class ExpectedDifference(NamedTuple):
    kind: Literal["missing", "relation"]
    check: str
    filed_state: Literal["filed_zero", "filed_blank", "filed_relation"] | None = None
    filed_check: str | None = None


EXPECTED_DIFFERENCES: dict[CellKey, ExpectedDifference] = {}

for case, carrier, years in (
    ("CLIENT-P1", "electricity_pv", (2022, 2023, 2024)),
    ("CLIENT-P2", "sunflower_husks", (2023, 2024, 2025)),
):
    for item_year in years:
        EXPECTED_DIFFERENCES[case, "impact de mediu", "total", item_year, None] = (
            ExpectedDifference("missing", f"factor.co2.{carrier}.", "filed_relation", "co2_sum")
        )

for item_year in (2022, 2023, 2024):
    EXPECTED_DIFFERENCES["CLIENT-P1", "TEP", "purchased_heat", item_year, None] = ExpectedDifference(
        "missing", f"carrier.purchased_heat.{item_year}", "filed_zero"
    )
    for carrier in ("water_potable", "water_industrial"):
        EXPECTED_DIFFERENCES["CLIENT-P1", "Consumuri specifice", carrier, item_year, None] = (
            ExpectedDifference("missing", f"energy.not_energy.{carrier}", "filed_zero")
        )
    EXPECTED_DIFFERENCES["CLIENT-A3", "Consumuri specifice", "purchased_heat", item_year, None] = (
        ExpectedDifference("missing", "energy.absent_carrier.purchased_heat", "filed_zero")
    )
    for month in (*range(1, 13), None):
        EXPECTED_DIFFERENCES["CLIENT-A3", "TEP", "ctl", item_year, month] = ExpectedDifference(
            "missing", f"carrier.ctl.{item_year}", "filed_zero"
        )

EXPECTED_DIFFERENCES["CLIENT-P1", "impact de mediu", "diesel", 2022, None] = ExpectedDifference(
    "relation", "impact_diesel_input"
)
EXPECTED_DIFFERENCES["CLIENT-P1", "impact de mediu", "petrol", 2022, None] = ExpectedDifference(
    "missing", "factor.co2.petrol.", "filed_zero"
)
EXPECTED_DIFFERENCES["CLIENT-P1", "impact de mediu", "lpg", 2023, None] = ExpectedDifference(
    "missing", "carrier.lpg.2023", "filed_zero"
)

for item_year, months in ((2023, (*range(1, 12), None)), (2024, (*range(1, 10), 11, None))):
    for month in months:
        for carrier in ("lpg", "total"):
            EXPECTED_DIFFERENCES["CLIENT-P2", "TEP", carrier, item_year, month] = ExpectedDifference(
                "missing",
                f"carrier.lpg.{item_year}.",
                "filed_relation" if carrier == "total" or month is None else "filed_zero",
                "tep_sum" if carrier == "total" else "lpg_monthly_sum" if month is None else None,
            )
    for sheet, label in (
        ("impact de mediu", "lpg"),
        ("Chelt-Cifra afaceri", "intensity"),
        ("Consumuri specifice", "total"),
    ):
        EXPECTED_DIFFERENCES["CLIENT-P2", sheet, label, item_year, None] = ExpectedDifference(
            "missing",
            f"carrier.lpg.{item_year}.",
            "filed_relation",
            {
                "impact de mediu": "lpg_co2_from_tep",
                "Chelt-Cifra afaceri": "filed_production_intensity",
                "Consumuri specifice": "filed_specific_total",
            }[sheet],
        )

for month in (*range(1, 13), None):
    EXPECTED_DIFFERENCES["CLIENT-P2", "TEP", "electricity_pv", 2025, month] = ExpectedDifference(
        "missing", "carrier.electricity_pv.2025", "filed_relation", "pv_annual_sum"
    )
for item_year in (2023, 2024, 2025):
    EXPECTED_DIFFERENCES["CLIENT-P2", "Consumuri specifice", "petrol", item_year, None] = (
        ExpectedDifference("relation", "diesel_specific")
    )
EXPECTED_DIFFERENCES["CLIENT-P2", "Chelt-Cifra afaceri", "intensity", 2025, None] = ExpectedDifference(
    "relation", "production_value_intensity"
)
EXPECTED_DIFFERENCES["CLIENT-A3", "Chelt-Cifra afaceri", "intensity", 2024, None] = (
    ExpectedDifference("relation", "scaled_intensity")
)
EXPECTED_DIFFERENCES["CLIENT-A3", "impact de mediu", "lpg", 2023, None] = ExpectedDifference(
    "missing", "carrier.lpg.2023", "filed_zero"
)
EXPECTED_DIFFERENCES["CLIENT-A3", "impact de mediu", "ctl", 2024, None] = ExpectedDifference(
    "missing", "carrier.ctl.2024", "filed_zero"
)
