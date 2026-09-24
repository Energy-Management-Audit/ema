"""A described measure with blank cells must remain visible for review."""

from pathlib import Path

from openpyxl import Workbook

from ema.energy_data.anexa import parse_anexa


def test_described_measure_without_year_or_values_is_reported(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Solutii EE existente"
    sheet["B3"] = "Descrierea măsurii"
    sheet["C3"] = "Data punerii în funcțiune"
    sheet["B4"] = "Înlocuirea pompei"
    path = tmp_path / "blank-measure.xlsx"
    workbook.save(path)

    parsed = parse_anexa(path)

    assert len(parsed.existing_measures) == 1
    assert parsed.existing_measures[0].description.ref.a1 == "Solutii EE existente!B4"
    assert parsed.existing_measures[0].commissioning_year is None
    assert any(issue.code == "commissioning_year_missing" for issue in parsed.issues)
