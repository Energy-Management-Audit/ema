"""The ch. 2-3 tables take their rows from the reviewed fields: one row per data row."""

from __future__ import annotations

from decimal import Decimal

from docx import Document
from docx.oxml.ns import qn

from ema.audit.chapter_tables import MISSING, TableSpec, fill_table
from ema.audit.chapter_tables_data import FAMILIES, boiler_rows, vehicle_rows, yearly
from ema.audit.render import ITERATED
from ema.core.review.models import Field


def _field(key: str, value: object, *, review: str = "pending", decimals: int = 0) -> Field:
    number = isinstance(value, int | Decimal)
    return Field.model_validate(
        {
            "id": key,
            "job_id": "job",
            "key": key,
            "label": key,
            "value_type": "number" if number else "text",
            "decimals": decimals,
            "value": value,
            "state": "supplied",
            "presence": "found",
            "review": review,
        }
    )


def _row(family: str, number: int, **cells: object) -> list[Field]:
    return [_field(f"{family}{number}.{role}", value) for role, value in cells.items()]


def test_yearly_follows_the_years_held_and_a_rejected_value_is_missing() -> None:
    table = yearly(
        [
            _field("audit.employees.2025", 379),
            _field("audit.employees.2023", 377),
            _field("audit.employees.2024", 376, review="rejected"),
            _field("audit.employees", 379),
        ],
        "audit.employees.",
    )
    assert table.years == [2023, 2024, 2025]
    assert table.rows == [["2023", "377"], ["2024", None], ["2025", "379"]]
    assert table.values == [377.0, None, 379.0]


def test_money_prints_as_in_her_documents() -> None:
    field = _field("turnover.2025", Decimal("405087623"), decimals=2)
    assert yearly([field], "turnover.").rows == [["2025", "405.087.623,00"]]


def test_boilers_have_no_resource_and_vehicles_then_forklifts_are_one_row_each() -> None:
    fields = [
        *_row("audit.boiler.", 1, name="Centrala A", process="Incalzire", count=2, power=500),
        *_row("audit.boiler.", 2, process="Apa calda", count=1),
        *_row("audit.vehicle.", 1, name="Autoturism", maker="Marca Z", type="308", count=42),
        *_row("audit.forklift.", 1, name="MARCA : Marca X", fuel="electric"),
        *_row("audit.forklift.", 1, type="TIP : ERE 220 / SERIA : 90120354"),
        *_row("audit.forklift.", 2, type="TIP : TFG 316"),
    ]
    assert boiler_rows(fields) == [
        ["Centrala A", "Incalzire", "2", "500", None],
        [None, "Apa calda", "1", None, None],
    ]
    assert vehicle_rows(fields) == [
        ["Autoturism Marca Z 308", "42", None],
        ["Autostivuitor Marca X ERE 220 (electric)", "1", None],
        ["Autostivuitor TFG 316", "1", None],
    ]


def _table() -> object:
    document = Document()
    table = document.add_table(rows=4, cols=3)
    for index, row in enumerate(table.rows):
        for cell in row.cells:
            cell.paragraphs[0].add_run("[de completat]" if index != 2 else "x")
    return table._tbl


def test_fill_clones_the_prototype_row_per_data_row_and_marks_missing_red() -> None:
    table = _table()
    spec = TableSpec("ch3.x", ("Nr", "Denumire", "Buc."), numbered=True)
    fill_table(table, spec, [["A", "1"], [None, "2"], ["C", None], ["D", "4"], ["E", "5"]])  # type: ignore[arg-type]
    rows = table.findall(qn("w:tr"))  # type: ignore[attr-defined]
    text = [
        ["".join(t.text or "" for t in c.iter(qn("w:t"))) for c in r.findall(qn("w:tc"))]
        for r in rows
    ]
    # header, then the data rows: the Nr column is the base's own and stays as it was
    assert text[0] == ["Nr", "Denumire", "Buc."]
    assert [row[1:] for row in text[1:]] == [
        ["A", "1"],
        [MISSING, "2"],
        ["C", MISSING],
        ["D", "4"],
        ["E", "5"],
    ]
    red = [
        run.find(qn("w:rPr")).find(qn("w:color")).get(qn("w:val"))  # type: ignore[union-attr]
        for run in rows[2].iter(qn("w:r"))
        if "".join(t.text or "" for t in run.iter(qn("w:t"))) == MISSING
    ]
    assert red == ["FF0000"]


def test_fewer_data_rows_remove_the_unused_prototype_rows() -> None:
    table = _table()
    spec = TableSpec("ch2.x", ("An", "Valoare", "Alta"))
    fill_table(table, spec, [["2023", "1", "2"]])  # type: ignore[arg-type]
    assert len(table.findall(qn("w:tr"))) == 2  # type: ignore[attr-defined]


def test_the_render_binds_every_family_it_reads() -> None:
    """A new row, or a decision on one, must make the render stale."""
    assert set(FAMILIES) <= set(ITERATED)
