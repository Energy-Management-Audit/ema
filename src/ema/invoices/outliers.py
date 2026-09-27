"""Explain unusually high monthly electricity consumption."""

from __future__ import annotations

from decimal import Decimal

OUTLIER_RATIO = Decimal("1.30")


def outliers(totals: dict[str, Decimal]) -> dict[str, tuple[Decimal, Decimal]]:
    marked: dict[str, tuple[Decimal, Decimal]] = {}
    for month, value in totals.items():
        year, number = map(int, month.split("-"))
        previous = f"{year - 1:04d}-12" if number == 1 else f"{year:04d}-{number - 1:02d}"
        following = f"{year + 1:04d}-01" if number == 12 else f"{year:04d}-{number + 1:02d}"
        neighbours = [totals[key] for key in (previous, following) if key in totals]
        if not neighbours:
            continue
        mean = sum(neighbours, Decimal(0)) / len(neighbours)
        if mean and value / mean >= OUTLIER_RATIO:
            marked[month] = (value / mean, mean)
    return marked
