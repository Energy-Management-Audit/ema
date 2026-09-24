"""S5 regression against local client workbooks and private cell snapshots."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from conftest import artifacts_path
from ema.energy_data.anexa import parse_anexa
from ema.energy_data.necesar import parse_necesar_info, to_dataset
from ema.energy_data.source import Located, normal

from .s3_book import Workbook
from .s3_book import year as filed_year

pytestmark = pytest.mark.golden

CASES = {
    "CLIENT-P1": (
        "piee/cases/piee-case-a/received/Necesar info 2025 - CLIENT-P1 - completat .xls",
        5,
        1,
        [],
    ),
    "CLIENT-A3": (
        "audit/cases/audit-case-c/received/Necesar info aferente anului 2025 - "
        "CLIENT-A3 - 16.03.2026.xls",
        6,
        1,
        [
            ("label_from_unit_cell", "Productii!B3"),
            ("table_header_ambiguous", "Autovehicule!F7"),
            ("table_header_ambiguous", "Autovehicule!G7"),
            ("table_header_ambiguous", "Autovehicule!H7"),
        ],
    ),
    "CLIENT-A1": (
        "audit/cases/audit-case-a/received/0.Necesar info CLIENT-A1 _2026.xls",
        6,
        3,
        [
            ("value_missing", "Cons energetice!B11"),
            ("value_missing", "Cons energetice!B26"),
            ("label_from_unit_cell", "Productia!B4"),
        ],
    ),
}


@pytest.mark.parametrize("case", list(CASES))
def test_read_matches_private_cell_snapshot(reference_library: Path, case: str) -> None:
    relative, carrier_count, year_count, expected_issues = CASES[case]
    path = reference_library / relative
    info = parse_necesar_info(path)
    assert len(info.carriers) == carrier_count
    assert all(len(block.years) == year_count for block in info.carriers.values())
    assert [(i.code, i.ref.a1 if i.ref else None) for i in info.issues] == expected_issues
    expected_path = artifacts_path("s5", "expected") / f"{case}.json"
    assert expected_path.exists(), f"Generate and review the local S5 snapshot: {expected_path}"
    snapshot = json.loads(expected_path.read_text())
    assert set(snapshot) == {carrier.value for carrier in info.carriers}
    for carrier, block in info.carriers.items():
        assert set(snapshot[carrier.value]) == {str(year) for year in block.years}
        for year, values in block.years.items():
            expected = snapshot[carrier.value][str(year)]
            assert len(values.months) == 12
            for month, filed in enumerate(expected["months"], 1):
                found = values.months[month - 1]
                if filed is None:
                    assert found is None
                else:
                    assert found is not None and found.value == pytest.approx(filed)
                if found is not None:
                    assert found.ref.row == expected["row"]
                    assert found.ref.col == month + 1
                    assert found.unit is not None
            total = values.total
            if expected["total"] is None:
                assert total is None
            else:
                assert total is not None and total.value == pytest.approx(expected["total"])
            if total is not None:
                assert total.ref.row == expected["row"]
                assert total.ref.col == 14
    dataset = to_dataset(info)
    assert len(dataset.carriers) == carrier_count + len(info.water)
    assert set(dataset.years) == {
        year for block in (*info.carriers.values(), *info.water.values()) for year in block.years
    }


@pytest.mark.parametrize("case", list(CASES))
def test_other_sheet_structure(reference_library: Path, case: str) -> None:
    info = parse_necesar_info(reference_library / CASES[case][0])
    dataset = to_dataset(info)
    assert all(item.name.ref.sheet for item in info.production)
    assert all(item.unit.ref.sheet for item in info.production)
    if case == "CLIENT-P1":
        assert len(info.water) == 3
        assert len(info.production) == 1
        assert not dataset.energy_costs_lei
    elif case == "CLIENT-A3":
        assert len(info.water) == 3
        assert len(info.other_consumption) == 5
        assert len(info.tables["autovehicule"].rows) == 22
        assert len(info.tables["cladiri"].rows) == 3
        assert len(dataset.energy_costs_lei) == 1
    else:
        assert len(info.water) == 2
        assert len(info.production) == 1 and len(info.production[0].years) == 3
        assert len(info.employees) == 3
        assert set(info.tables) == {
            "autovehicule",
            "cladiri",
            "echipamente 1",
            "echipamente 2",
            "echipamente 3",
        }
        assert len(info.tables["echipamente 1"].rows) == 34
        assert sum(bool(row.continuation) for row in info.tables["echipamente 1"].rows) == 18
        assert len(dataset.energy_costs_lei) == 3


@pytest.mark.parametrize("case", list(CASES))
def test_consumption_blocks_match_private_inventory(reference_library: Path, case: str) -> None:
    inventory = artifacts_path("s5", "blocks.txt")
    assert inventory.exists(), f"Review the local S5 block inventory: {inventory}"
    expected: set[tuple[str, str, int, str]] = set()
    case_lines = 0
    for line in inventory.read_text().splitlines():
        fields = line.split("\t")
        assert len(fields) == 8
        if fields[0] == case:
            case_lines += 1
            expected.add((fields[1], fields[3], int(fields[4]), fields[6]))
    assert expected and len(expected) == case_lines
    info = parse_necesar_info(reference_library / CASES[case][0])
    found: set[tuple[str, str, int, str]] = set()
    for carrier, block in (*info.carriers.items(), *info.water.items()):
        for year, values in block.years.items():
            located = next((value for value in (*values.months, values.total) if value), None)
            assert located is not None, (case, carrier.value, year)
            found.add(
                (
                    block.label.ref.a1,
                    carrier.value,
                    year,
                    f"{located.ref.sheet}!A{located.ref.row}",
                )
            )
    assert found == expected


def _prelucrare_years(path: Path) -> set[int]:
    book = Workbook.open(path)
    return {
        found
        for row in book.sheet("TEP")
        for cell in row[:3]
        if (found := filed_year(cell)) is not None
    }


@pytest.mark.parametrize("case", ["CLIENT-P1", "CLIENT-A3"])
def test_delivered_prelucrare_has_no_overlapping_energy_year(
    reference_library: Path, case: str
) -> None:
    relative = CASES[case][0]
    info = parse_necesar_info(reference_library / relative)
    received = (reference_library / relative).parent
    prelucrare = next(received.glob("*Prelucrare date*"))
    years = _prelucrare_years(prelucrare)
    source_years = {year for block in info.carriers.values() for year in block.years}
    assert source_years.isdisjoint(years)
    print(f"{case}: level 1; no overlapping carrier year with delivered Prelucrare date")


def _same_unit(first: Located, second: Located) -> bool:
    a = normal(first.unit or "").removesuffix(" an")
    b = normal(second.unit or "").removesuffix(" an")
    return a == b


def test_CLIENT-P1_anexa_cross_document_check(reference_library: Path) -> None:
    received = reference_library / "piee/cases/piee-case-a/received"
    necesar = parse_necesar_info(received / Path(CASES["CLIENT-P1"][0]).name)
    anexa = parse_anexa(next(received.glob("*Anexa*.xlsx")))
    matches: list[str] = []
    mismatches: list[str] = []
    uncomparable: list[str] = []
    for carrier, block in necesar.carriers.items():
        total = block.years[2025].total
        filed = anexa.annual.get(f"{carrier.value}_raw")
        if filed is None and carrier.value in {"electricity_grid", "electricity_pv"}:
            filed = anexa.annual.get(f"{carrier.value}_mwh")
        if total is None or filed is None or not _same_unit(total, filed):
            uncomparable.append(carrier.value)
        elif math.isclose(float(total.value), float(filed.value), rel_tol=0, abs_tol=0.01):
            matches.append(carrier.value)
        else:
            mismatches.append(carrier.value)
    assert set(matches) == {"natural_gas", "electricity_grid", "electricity_pv", "petrol", "diesel"}
    assert not mismatches
    assert not uncomparable
    print(
        "CLIENT-P1 Anexa level 1 cross-document: "
        f"matches={matches}, mismatches={mismatches}, uncomparable={uncomparable}"
    )
