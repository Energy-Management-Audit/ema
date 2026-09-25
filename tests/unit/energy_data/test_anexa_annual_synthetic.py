"""Annual annex totals and fuel units are found from labels rather than addresses."""

from pathlib import Path

from openpyxl import Workbook, load_workbook

from ema.energy_data.anexa import parse_anexa


def test_annual_totals_and_fuels_follow_shifted_labels(tmp_path: Path) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Date anuale"
    sheet.cell(4, 2, "anului anterior")
    sheet.cell(4, 4, 2025)
    sheet.cell(7, 2, "CONSUM DE ENERGIE TOTAL ANUAL")
    sheet.cell(8, 3, "tep/an")
    sheet.cell(8, 4, 4.5)
    sheet.cell(11, 2, "ENERGIE ELECTRICĂ** – Consumul total anual din SEN")
    sheet.cell(11, 3, "tep/an")
    sheet.cell(11, 4, 3.4)
    sheet.cell(12, 3, "MWh/an")
    sheet.cell(12, 4, 40)
    sheet.cell(18, 3, "Gaze naturale")
    sheet.cell(19, 3, "MWh/an")
    sheet.cell(20, 3, 50)
    sheet.cell(21, 3, "tep/an")
    sheet.cell(22, 3, 4.3)
    path = tmp_path / "anexa.xlsx"
    book.save(path)

    parsed = parse_anexa(path)
    assert parsed.year.value == 2025
    assert parsed.year.ref.a1 == "Date anuale!D4"
    assert parsed.annual["total_tep"].value == 4.5
    assert parsed.annual["electricity_grid_mwh"].value == 40
    assert parsed.annual["natural_gas_raw"].value == 50
    assert parsed.annual["natural_gas_raw"].unit == "MWh/an"
    assert parsed.annual["natural_gas_tep"].value == 4.3
    assert any(issue.code == "sheet_missing" for issue in parsed.issues)

    duplicate = load_workbook(path)
    duplicate["Date anuale"].cell(18, 5, "Gaze naturale")
    duplicate.save(path)
    conflicted = parse_anexa(path)
    assert "natural_gas_raw" not in conflicted.annual
    assert any(issue.code == "carrier_ambiguous" for issue in conflicted.issues)
