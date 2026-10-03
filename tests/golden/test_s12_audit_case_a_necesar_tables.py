"""audit_case_a: the ch. 2-3 tables and charts hold what the Necesar info sheets hold.

The oracle reads the workbook cells itself, found by their labels; no value is written here.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

import pytest
from docx import Document
from docx.oxml.ns import qn
from lxml import etree
from tests.golden.cases import case_path
from tests.workspace_jobs import create_job

from ema.audit.base import build_base
from ema.audit.base_package import package_issues, scrub_package
from ema.audit.chapter_tables import write_charts, write_tables
from ema.audit.heading_titles import MARKER
from ema.audit.read import read_dossier
from ema.core.office.sheets import Book, Sheet, open_book
from ema.core.workspace import Workspace
from ema.energy_data.source import normal

from .test_s10b_audit_base import _audit_case_a_plan, _identity, _references

pytestmark = pytest.mark.golden

CELL = qn("w:tc")


def _grid(sheet: Sheet) -> list[list[Any]]:
    return [
        [sheet.value(row, col).value for col in range(1, sheet.max_col + 1)]
        for row in range(1, sheet.max_row + 1)
    ]


def _row_with(grid: list[list[Any]], label: str) -> int:
    """The first row holding a cell that starts with the label."""
    return next(
        i
        for i, row in enumerate(grid)
        if any(isinstance(cell, str) and normal(cell).startswith(label) for cell in row)
    )


def _column(grid: list[list[Any]], header: int, label: str) -> int:
    row = grid[header]
    return next(
        i for i, cell in enumerate(row) if isinstance(cell, str) and normal(cell).startswith(label)
    )


def _years(grid: list[list[Any]], row: int) -> dict[int, int]:
    return {
        col: int(cell)
        for col, cell in enumerate(grid[row])
        if isinstance(cell, int | float) and 2000 <= cell <= 2100
    }


def _num(value: Any) -> float:
    """A cell's number; the client types some as text with non-breaking spaces."""
    return float(str(value).replace("\xa0", "").strip()) if isinstance(value, str) else float(value)


def _thousands(number: float, decimals: int) -> str:
    text = f"{number:,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def _sheet_with(book: Book, label: str) -> list[list[Any]]:
    for name in book.sheet_names:
        grid = _grid(book.sheet(name))
        if any(
            isinstance(cell, str) and normal(cell).startswith(label) for row in grid for cell in row
        ):
            return grid
    raise AssertionError(f"no sheet has {label!r}")


def _table_cells(table: Any) -> list[list[str]]:
    return [
        ["".join(t.text or "" for t in cell.iter(qn("w:t"))) for cell in row.findall(CELL)]
        for row in table.findall(qn("w:tr"))
    ]


def _cell(grid: list[list[Any]], header: int, row: int, label: str) -> Any:
    return grid[row][_column(grid, header, label)]


def _text(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def _expected(book: Book) -> dict[str, list[list[str]]]:
    employees = _sheet_with(book, "numar de salariati")
    row = _row_with(employees, "numar de salariati")
    year_row = next(i for i, r in enumerate(employees) if len(_years(employees, i)) >= 2)
    people = {year: employees[row][col] for col, year in _years(employees, year_row).items()}
    economics = _sheet_with(book, "cifra de afaceri")
    row = _row_with(economics, "cifra de afaceri")
    year_row = _row_with(economics, "anul")
    money = {year: economics[row][col] for col, year in _years(economics, year_row).items()}

    boilers = _sheet_with(book, "proces de fabricatie")
    head = _row_with(boilers, "proces de fabricatie")
    number = _column(boilers, head, "nr crt")
    boiler_rows = [
        [
            _text(_cell(boilers, head, i, "denumire")),
            _text(_cell(boilers, head, i, "proces de fabricatie")),
            _text(_cell(boilers, head, i, "nr buc")),
            _text(_cell(boilers, head, i, "putere instalata")),
            "n.d.",
        ]
        for i in range(head + 1, len(boilers))
        if isinstance(boilers[i][number], int | float)
    ]

    fleet = _sheet_with(book, "denumire autovehicul")
    head = _row_with(fleet, "denumire autovehicul")
    vehicles = [
        [
            " ".join(
                _text(_cell(fleet, head, i, label))
                for label in ("denumire autovehicul", "producator", "tip")
                if _cell(fleet, head, i, label) is not None
            ),
            _text(_cell(fleet, head, i, "nr buc")),
            "n.d.",
        ]
        for i in range(head + 1, len(fleet))
        if _cell(fleet, head, i, "denumire autovehicul") is not None
    ]
    lifts = _sheet_with(book, "greutate")
    head = _row_with(lifts, "nr")
    number = _column(lifts, head, "nr")
    forklifts: list[list[str]] = []
    for i in range(head + 1, len(lifts)):
        if not isinstance(lifts[i][number], int | float):
            continue
        # a second line under the unit, in the name column, names its model
        below = lifts[i + 1] if i + 1 < len(lifts) else []
        detail = below[2] if below and below[number] is None and below[2] is not None else None
        model = re.split(r"(?i)\s*/\s*seria", _text(detail))[0] if detail is not None else ""
        parts = [
            re.sub(r"(?i)^\s*marca\s*:\s*", "", _text(lifts[i][2])),
            re.sub(r"(?i)^\s*tip\s*:\s*", "", model),
        ]
        forklifts.append([" ".join(p for p in parts if p), _text(_cell(lifts, head, i, "comb"))])
    return {
        "employees": [[str(y), _thousands(_num(v), 0)] for y, v in sorted(people.items())],
        "turnover": [[str(y), _thousands(_num(v), 2)] for y, v in sorted(money.items())],
        "boilers": boiler_rows,
        "vehicles": [[v[0], v[1], v[2]] for v in vehicles],
        "forklifts": [[f"Autostivuitor {name} ({fuel})", "1", "n.d."] for name, fuel in forklifts],
    }


def _chart_values(docx: Path) -> list[tuple[list[str], list[float]]]:
    """Each chart's categories and values, from the caches Word draws them from."""
    ns = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
    result: list[tuple[list[str], list[float]]] = []
    with zipfile.ZipFile(docx) as package:
        for name in sorted(package.namelist()):
            if not re.fullmatch(r"word/charts/chart\d+\.xml", name):
                continue
            root = etree.fromstring(package.read(name))
            for series in root.iterfind(".//c:ser", ns):
                categories = [str(v.text) for v in series.iterfind("c:cat//c:pt/c:v", ns)]
                values = [float(str(v.text)) for v in series.iterfind("c:val//c:pt/c:v", ns)]
                result.append((categories, values))
    return result


def test_ch2_and_ch3_tables_follow_the_necesar_sheets(
    reference_library: Path, tmp_path: Path
) -> None:
    received = reference_library / case_path("audit-case-a", "received")
    necesar = next(received.glob("*Necesar info*.xls"))
    book = open_book(necesar)
    try:
        expected = _expected(book)
    finally:
        book.close()
    # the sources hold rows, so the count the data gives is not the base's own
    assert len(expected["boilers"]) and len(expected["vehicles"]) + len(expected["forklifts"]) > 18

    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "audit-case-a", 2026)
    fields = list(read_dossier(ws, job, necesar).fields)
    source, prototype = _references(reference_library)
    identity = _identity(source)
    base = tmp_path / "base.docx"
    build_base(
        _audit_case_a_plan(reference_library),
        base_document=source,
        measurement_prototype=prototype,
        output=base,
        base_identity=identity,
    )
    ch2, charted, output = tmp_path / "ch2.docx", tmp_path / "charted.docx", tmp_path / "out.docx"
    write_tables(base, ch2, chapter="ch2", fields=fields)
    write_charts(ch2, charted, fields=fields, chart_source=source)
    write_tables(charted, output, chapter="ch3", fields=fields)
    scrub_package(output)
    assert not package_issues(output, identity)

    tables = [
        _table_cells(element) for element in Document(str(output)).element.body.iter(qn("w:tbl"))
    ]
    filled = [t for t in tables if t and not any(MARKER in c for row in t for c in row)]
    by_header = {tuple(t[0]): t for t in filled}
    employees = by_header[("An referință", "Numărul mediu total de angajați")]
    turnover = by_header[("Anul", "Valoare - lei")]
    assert employees[1:] == expected["employees"]
    assert turnover[1:] == expected["turnover"]

    boilers = next(t for h, t in by_header.items() if h[1] == "Denumire + tip echipament")
    # header, the base's blank spacer row, then one row per boiler; its first column is numbered
    assert [row[1:] for row in boilers[2:]] == expected["boilers"]
    assert boilers[0][5] == "Resursa consumată"

    fleet = next(t for h, t in by_header.items() if h[1] == "Tip autovehicul")
    assert [row[1:] for row in fleet[1:]] == expected["vehicles"] + expected["forklifts"]

    # a table's own row count follows the data, not the base's 4/18 rows
    assert len(fleet) - 1 == len(expected["vehicles"]) + len(expected["forklifts"])

    # the second equipment table and the generic tables hold no Necesar data: untouched
    assert any(any(MARKER in c for row in t for c in row) for t in tables)

    charts = _chart_values(output)
    people = [float(row[1].replace(".", "")) for row in expected["employees"]]
    money = [float(row[1].replace(".", "").replace(",", ".")) for row in expected["turnover"]]
    years = [row[0] for row in expected["employees"]]
    assert (years, people) in charts
    assert ([row[0] for row in expected["turnover"]], money) in charts
