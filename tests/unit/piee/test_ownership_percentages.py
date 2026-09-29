"""Ownership percentages are parsed from the source, never inferred from flags or labels."""

from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from ema.energy_data.anexa import parse_anexa
from ema.piee.identity import identity_values


def _annex(path: Path, state: object, private: object, number_format: str = "General") -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Date generale"
    sheet.append(["Stat", state, "Privat", private])
    for column in (2, 4):
        sheet.cell(1, column).number_format = number_format
    book.save(path)


@pytest.mark.parametrize(
    "raw,number_format,expected",
    [
        ("37,5 %", "General", "37,5%"),
        ("37.5%", "General", "37,5%"),
        (0.375, "0.0%", "37,500%"),
        (0, "0%", "0%"),
        (0, "General", None),
        (1, "General", None),
        ("DA", "General", None),
        ("<label>", "General", None),
        (None, "General", None),
        (1, '0"%"', None),
        (1, r"0\%", None),
        ("200%", "General", None),
    ],
)
def test_ownership_reads_only_source_percentages(
    tmp_path: Path, raw: object, number_format: str, expected: str | None
) -> None:
    path = tmp_path / "annex.xlsx"
    _annex(path, raw, "62,5%", number_format)
    data = parse_anexa(path)
    found = data.identity.get("ownership_state")
    assert (str(found.value) if found else None) == expected
    if expected is None:
        assert any(
            item.code == "ownership_flag" and item.detail == "ownership_state"
            for item in data.issues
        )
        assert identity_values(data, date(2026, 1, 1))["ownership"] is None
    assert str(data.identity["ownership_private"].value) == "62,5%"


def test_a_neighbouring_label_is_never_a_percentage(tmp_path: Path) -> None:
    path = tmp_path / "annex.xlsx"
    _annex(path, None, "100%")
    data = parse_anexa(path)
    assert "ownership_state" not in data.identity
    assert data.identity["ownership_private"].value == "100%"
