"""Level 1 regression: all fields against the independent workbook dump.

The dump contains source cells, not a document the auditor delivered. Hyperlink targets
are checked separately against workbook relationships because the dump omits them.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

import pytest
from tests.golden.anexa_location import _field_location, _measure_location, _monthly_location

from ema.core.office.sheets import open_book
from ema.energy_data.anexa import parse_anexa
from ema.energy_data.anexa_cells import Measure
from ema.energy_data.source import Located, ReaderIssue

pytestmark = pytest.mark.golden

_COMMON_ANNUAL = {
    "total_tep",
    "electricity_grid_tep",
    "electricity_grid_mwh",
    "purchased_heat_tep",
    "electricity_pv_mwh",
    "natural_gas_raw",
    "natural_gas_tep",
    "fuel_oil_raw",
    "fuel_oil_tep",
    "petrol_raw",
    "petrol_tep",
    "diesel_raw",
    "diesel_tep",
    "coal_raw",
    "coal_tep",
}
_COMMON_IDENTITY = {
    "name",
    "address",
    "cui",
    "phone",
    "fax",
    "website",
    "caen_code",
    "caen_description",
}
_COMMON_MONTHLY = {
    "electricity_grid",
    "natural_gas",
    "fuel_oil",
    "petrol",
    "diesel",
    "coal",
}
# Reviewed field inventory and row counts from the independent dump. No client values.
_CASES = {
    "CLIENT-P1": (
        _COMMON_IDENTITY | {"contact_person", "ownership_state", "ownership_private"},
        _COMMON_ANNUAL | {"purchased_heat_gcal", "clu_raw", "clu_tep"},
        _COMMON_MONTHLY | {"purchased_heat", "clu", "water_industrial"},
        (16, 25),
    ),
    "CLIENT-X3": (
        _COMMON_IDENTITY
        | {"contact_person", "consumer_contact_person", "ownership_state", "website_target"},
        _COMMON_ANNUAL | {"purchased_heat_gcal", "clu_raw", "clu_tep"},
        _COMMON_MONTHLY | {"clu", "water_industrial"},
        (7, 7),
    ),
    "CLIENT-P2": (
        _COMMON_IDENTITY | {"contact_person"},
        _COMMON_ANNUAL
        | {"purchased_heat_gcal", "lpg_raw", "lpg_tep", "biomass_raw", "biomass_tep"},
        _COMMON_MONTHLY | {"purchased_heat", "lpg", "biomass"},
        (18, 11),
    ),
    "CLIENT-X1": (
        _COMMON_IDENTITY,
        (_COMMON_ANNUAL - {"purchased_heat_gcal"}) | {"clu_raw", "clu_tep"},
        _COMMON_MONTHLY | {"purchased_heat", "clu", "water_potable"},
        (23, 15),
    ),
    "CLIENT-X2": (
        _COMMON_IDENTITY | {"contact_person", "ownership_private"},
        _COMMON_ANNUAL | {"purchased_heat_gcal", "clu_raw", "clu_tep", "lpg_raw", "lpg_tep"},
        _COMMON_MONTHLY | {"purchased_heat", "clu", "lpg", "water_industrial"},
        (10, 5),
    ),
}


def _case(reference_library: Path, fragment: str) -> Path:
    return next((reference_library / "piee" / "anexa-2-3-2025").glob(f"*{fragment}*.xls*"))


def _dump(reference_library: Path, path: Path) -> dict[str, list[list[str]]]:
    source = reference_library / "_analysis" / "anexa_dump.json"
    return json.loads(source.read_text(encoding="utf-8"))[str(path.relative_to(reference_library))]


def _source(sheets: dict[str, list[list[str]]], item: Located) -> str:
    row = sheets[item.ref.sheet][item.ref.row - 1]
    return row[item.ref.col - 1] if item.ref.col <= len(row) else ""


def _same_source(sheets: dict[str, list[list[str]]], item: Located) -> None:
    raw = _source(sheets, item)
    assert raw, item.ref.a1
    if isinstance(item.value, str):
        assert item.value == raw, item.ref.a1
    else:
        try:
            expected = float(raw.replace(" ", "").replace("\u00a0", "").replace(",", "."))
        except ValueError:
            assert str(item.value) == raw, item.ref.a1
        else:
            matches = math.isclose(float(item.value), expected, rel_tol=1e-12, abs_tol=1e-12)
            assert matches, item.ref.a1


def _ownership_source(sheets: dict[str, list[list[str]]], item: Located, path: Path) -> None:
    raw = _source(sheets, item)
    if raw.strip().endswith("%"):
        expected = Decimal(raw.strip().removesuffix("%").strip().replace(",", "."))
    else:
        book = open_book(path)
        try:
            cell = book.sheet(item.ref.sheet).value(item.ref.row, item.ref.col)
            assert cell.number_format == "0%"
            expected = Decimal(raw) * 100
        finally:
            book.close()
    assert item.unit == "%" and str(item.value).endswith("%")
    assert Decimal(str(item.value).removesuffix("%").replace(",", ".")) == expected


def _ownership_flags(
    sheets: dict[str, list[list[str]]], issues: list[ReaderIssue], fragment: str
) -> None:
    # F2 rejects the filed flags/neighboring label rather than inventing percentages.
    rejected = {
        "CLIENT-X1": {"ownership_state", "ownership_private"},
        "CLIENT-X2": {"ownership_state"},
    }.get(fragment, set())
    flags = [issue for issue in issues if issue.code == "ownership_flag"]
    assert {issue.detail for issue in flags} == rejected
    for issue in flags:
        assert issue.ref is not None
        raw = sheets[issue.ref.sheet][issue.ref.row - 1][issue.ref.col - 1]
        assert raw.strip() and "%" not in raw


def _measure_rows(sheets: dict[str, list[list[str]]], name: str, description_col: int) -> set[int]:
    rows = sheets[name]
    header = next(
        index
        for index, row in enumerate(rows, 1)
        if any("descrierea măsurii" in value.lower() for value in row[:8])
    )
    return {
        index
        for index, row in enumerate(rows[header:], header + 1)
        if description_col <= len(row)
        and row[description_col - 1].strip()
        and not row[description_col - 1]
        .strip()
        .lower()
        .startswith(("descrierea", "măsuri pe termen", "total", "data trimiterii"))
    }


def _plain(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c)
    )


def _measure_expected_keys(sheets: dict[str, list[list[str]]], name: str, row: int) -> set[str]:
    rows = sheets[name]
    header = max(
        index
        for index, values in enumerate(rows, 1)
        if index < row and any("descrierea măsurii" in value.lower() for value in values[:8])
    )
    headings = rows[header - 1]
    unit_rows = rows[header : min(header + 2, len(rows))]
    data = rows[row - 1]
    keys: set[str] = set()
    for col in range(min(len(headings), len(data))):
        if not re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", data[col].strip().replace(" ", "")):
            continue
        title = _plain(headings[col])
        unit = " ".join(
            re.findall(
                r"[a-z0-9]+",
                _plain(
                    next(
                        (values[col] for values in unit_rows if col < len(values) and values[col]),
                        "",
                    )
                ),
            )
        )
        if title.startswith(("durata de recuperare", "estimarea duratei de recuperare")):
            keys.add("payback_years")
        elif title.startswith(("costul investitiei", "costul aplicarii masurii")):
            keys.add("investment_thousand_lei")
        elif unit.startswith("mwh an"):
            keys.add("saving_mwh")
        elif unit.startswith(("tep an", "t e p an")):
            keys.add("saving_tep")
        elif title.startswith("economia de cost"):
            keys.add("saving_thousand_lei")
    return keys


def _check_measures(
    sheets: dict[str, list[list[str]]], measures: list[Measure], issues: list[ReaderIssue]
) -> None:
    assert measures
    name = measures[0].description.ref.sheet
    col = measures[0].description.ref.col
    assert {item.description.ref.row for item in measures} == _measure_rows(sheets, name, col)
    for measure in measures:
        assert set(measure.values) == _measure_expected_keys(
            sheets, name, measure.description.ref.row
        )
        _same_source(sheets, measure.description)
        _measure_location(sheets, measure.description, "description")
        if measure.location is not None:
            _same_source(sheets, measure.location)
            _measure_location(sheets, measure.location, "location")
        if measure.commissioning_year is not None:
            _same_source(sheets, measure.commissioning_year)
            _measure_location(sheets, measure.commissioning_year, "commissioning_year")
            assert 1990 <= measure.commissioning_year.value <= 2100
        else:
            assert any(
                issue.code == "commissioning_year_missing"
                and issue.ref is not None
                and issue.ref.row == measure.description.ref.row
                for issue in issues
            )
        for key, value in measure.values.items():
            _same_source(sheets, value)
            _measure_location(sheets, value, key)


@pytest.mark.parametrize("fragment", list(_CASES))
def test_complete_fields_match_source_dump(reference_library: Path, fragment: str) -> None:
    path = _case(reference_library, fragment)
    sheets = _dump(reference_library, path)
    parsed = parse_anexa(path)
    if fragment == "CLIENT-X2":
        assert "CHESTIONAR DE ANALIZĂ" in sheets["Info companie"][0][0]
    identity, annual, monthly, counts = _CASES[fragment]
    assert set(parsed.identity) == identity
    assert set(parsed.annual) == annual
    assert set(parsed.monthly) == monthly
    assert (len(parsed.existing_measures), len(parsed.planned_measures)) == counts
    _ownership_flags(sheets, parsed.issues, fragment)
    assert parsed.year is not None
    _same_source(sheets, parsed.year)
    _field_location(sheets, "year", parsed.year)

    for key, item in parsed.identity.items():
        if key == "website_target":
            book = open_book(path)
            try:
                assert (
                    book.sheet(item.ref.sheet).value(item.ref.row, item.ref.col).hyperlink
                    == item.value
                )
            finally:
                book.close()
        elif key.startswith("ownership_"):
            _ownership_source(sheets, item, path)
        else:
            _same_source(sheets, item)
        _field_location(sheets, key, item)
    for key, item in parsed.annual.items():
        _same_source(sheets, item)
        _field_location(sheets, key, item)
    for carrier, values in parsed.monthly.items():
        assert set(values) == set(range(1, 13))
        for month, item in values.items():
            assert item.unit is not None
            _same_source(sheets, item)
            _monthly_location(sheets, carrier, month, item)

    assert set(parsed.audit) == {"last_audit", "auditor", "boundary"}
    for key, item in parsed.audit.items():
        _same_source(sheets, item)
        _field_location(sheets, key, item)

    for measures in (parsed.existing_measures, parsed.planned_measures):
        _check_measures(sheets, measures, parsed.issues)
