"""The bookmarked analysis tables follow the approved PIEE presentation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from docx.oxml.ns import qn
from tests.golden.cases import case_path

from conftest import artifacts_path
from ema.core.office.anchors import AnchorLedger
from ema.core.office.base_map import load as load_map
from ema.core.office.numbers_ro import format_number
from ema.core.office.package import read_parts, xml
from ema.piee.dataset import load
from ema.piee.tables import _monthly, render_tables


def _tables(path: Path) -> list[tuple[int, list[list[str]]]]:
    body = xml(read_parts(path), "word/document.xml").find(qn("w:body"))
    assert body is not None
    return [
        (
            index,
            [
                [
                    "".join(node.text or "" for node in cell.iter(qn("w:t")))
                    for cell in row.findall(qn("w:tc"))
                ]
                for row in element.findall(qn("w:tr"))
            ],
        )
        for index, element in enumerate(body, 1)
        if element.tag == qn("w:tbl")
    ]


@pytest.mark.golden
def test_piee_case_a_monthly_and_equivalent_tables_match_approved(tmp_path: Path) -> None:
    reference = os.environ.get("EMA_REFERENCE")
    if reference is None:
        pytest.fail("EMA_REFERENCE is required for the S8 golden")
    case = Path(reference) / case_path("piee-case-a")
    data = load(
        2025,
        next(case.rglob("Anexa*.xlsx")),
        next(case.rglob("Necesar*.xls")),
        next(case.rglob("*Prelucrare*.xls")),
    )
    base = artifacts_path("s8", "base")
    mapping = load_map(base / "base-map.json")
    output = tmp_path / "tables.docx"
    render_tables(base / "piee-master.docx", data, output, AnchorLedger(mapping.variable_slots))
    original = _tables(base / "piee-master.docx")
    actual = dict(_tables(output))
    approved = _tables(next((case / "generated").glob("*.docx")))
    for table_number in (49, 51, 104, 106, 138, 140, 184, 186, 221, 223):
        ordinal = next(i for i, (index, _) in enumerate(original) if index == table_number)
        expected = [list(row) for row in approved[ordinal][1][1:]]
        if table_number == 104:
            # F12 changes one authored binary-rounding tie to half-up, from its source.
            raw = _monthly(data, 6)[0]
            assert raw is not None
            old = f"{raw:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
            assert expected[1][1] == old
            expected[1][1] = format_number(raw, 2)
        assert actual[table_number][1:] == expected
    equivalent = actual[277][1:]
    candidates = [cells[1:] for _, cells in approved if len(cells) == 4 and len(cells[0]) == 5]
    assert candidates == [equivalent]
