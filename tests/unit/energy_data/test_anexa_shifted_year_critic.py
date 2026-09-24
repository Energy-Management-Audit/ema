"""A reporting year remains discoverable when the form title moves."""

from pathlib import Path

from openpyxl import Workbook

from ema.energy_data.anexa import parse_anexa


def test_reporting_year_follows_shifted_title(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Date anuale"
    sheet["B3"] = "Date aferente anului anterior"
    sheet["C3"] = 2025
    path = tmp_path / "shifted.xlsx"
    workbook.save(path)

    parsed = parse_anexa(path)

    assert parsed.year is not None
    assert parsed.year.value == 2025
    assert parsed.year.ref.a1 == "Date anuale!C3"
