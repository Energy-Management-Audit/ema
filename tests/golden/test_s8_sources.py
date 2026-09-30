"""Real PIEE inputs exercise source precedence without storing client values."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.golden.cases import case_path

from ema.core.office.sheets import open_book
from ema.energy_data.carriers import Carrier
from ema.piee.dataset import load

pytestmark = pytest.mark.golden


def _only(folder: Path, pattern: str) -> Path:
    matches = list(folder.rglob(pattern))
    assert len(matches) == 1
    return matches[0]


def test_piee_case_a_sources_reconcile_to_filed_annual(reference_library: Path) -> None:
    folder = reference_library / case_path("piee-case-a")
    necesar = _only(folder, "Necesar*.xls")
    book = open_book(necesar)
    try:
        assert any(
            book.sheet(name).value(1, 1).number_format is not None for name in book.sheet_names
        )
    finally:
        book.close()
    result = load(2025, _only(folder, "Anexa*.xlsx"), necesar, _only(folder, "*Prelucrare*.xls"))
    assert result.annual_check.status == "match"
    assert result.necesar_status == "received"
    assert result.disagreements


def test_piee_case_b_prelucrare_covers_missing_necesar_and_exposes_internal_conflict(
    reference_library: Path,
) -> None:
    folder = reference_library / case_path("piee-case-b")
    result = load(2025, _only(folder, "Anexa*.xlsx"), None, _only(folder, "*Prelucrare*.xlsx"))
    assert result.dataset.years == (2023, 2024, 2025)
    assert result.necesar_status.startswith("not needed: covered by Prelucrare")
    assert result.annual_check.status == "match"
    assert Carrier.biomass not in result.dataset.carriers
    assert Carrier.sunflower_husks in result.dataset.carriers
    assert any(item.key.startswith("tep.internal_total.") for item in result.disagreements)


def test_piee_case_b_delivered_unit_converts_every_production_reading(
    reference_library: Path,
) -> None:
    folder = reference_library / case_path("piee-case-b")
    anexa = _only(folder, "Anexa*.xlsx")
    prelucrare = _only(folder, "*Prelucrare*.xlsx")
    previous = reference_library / case_path("piee-case-b", "final")
    source = load(2025, anexa, None, prelucrare)
    presented = load(2025, anexa, None, prelucrare, previous)
    conversion = presented.production_conversion
    assert conversion is not None
    assert (conversion.source_unit, conversion.presentation_unit, conversion.multiplier) == (
        "mii tone",
        "tone",
        1000.0,
    )
    for product, years in source.dataset.production.items():
        for year, series in years.items():
            result = presented.dataset.production[product][year]
            assert result.months.keys() == series.months.keys()
            assert all(
                result.months[month].value == reading.value * conversion.multiplier
                for month, reading in series.months.items()
                if reading.value is not None
            )
