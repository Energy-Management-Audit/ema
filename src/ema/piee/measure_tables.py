"""Clone authored measure rows and fill them from Anexa evidence."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
from pathlib import Path

from docx.oxml.ns import qn
from lxml import etree

from ema.core.office.anchor_targets import find_row
from ema.core.office.anchors import AnchorLedger, strip
from ema.core.office.cell_text import set_cell_text
from ema.core.office.package import encoded, read_parts, write_parts, xml
from ema.energy_data.anexa_cells import Measure
from ema.energy_data.source import Located
from ema.piee.dataset import PieeData
from ema.piee.measures import calculated_payback
from ema.piee.number import prototype_number


def _text(value: Located | None) -> str | None:
    return str(value.value).strip() if value is not None and str(value.value).strip() else None


def _number(row: Measure, key: str, decimals: int = 2) -> str | None:
    found = row.values.get(key)
    if found is None or not isinstance(found.value, int | float):
        return None
    return prototype_number(found.value, decimals)


def _payback(row: Measure) -> str | None:
    filed = _number(row, "payback_years")
    if filed is not None:
        return filed
    calculated = calculated_payback(row)
    return prototype_number(calculated, 2) if calculated is not None else None


def _audit_row(row: Measure) -> tuple[str | None, ...]:
    return (
        _text(row.description),
        _number(row, "saving_tep"),
        None,
        _number(row, "investment_thousand_lei"),
        _payback(row),
    )


def _solution_row(row: Measure) -> tuple[str | None, ...]:
    return (
        _text(row.description),
        _text(row.commissioning_year),
        _payback(row),
        _number(row, "investment_thousand_lei"),
        _number(row, "saving_mwh"),
        _number(row, "saving_tep"),
    )


def _replace_rows(
    root: etree._Element,
    table_number: int,
    rows: tuple[tuple[str | None, ...], ...],
    ledger: AnchorLedger,
) -> None:
    prototype = find_row([root], f"table_{table_number}_rows")
    table = prototype.getparent()
    if table is None or table.tag != qn("w:tbl"):
        raise ValueError("measure row is outside its table")
    authored = table.findall(qn("w:tr"))
    first = authored.index(prototype)
    for old in authored[first:]:
        table.remove(old)
    for values in rows or ((None,) * len(prototype.findall(qn("w:tc"))),):
        clone = copy.deepcopy(prototype)
        strip([clone])
        cells = clone.findall(qn("w:tc"))
        if len(cells) != len(values):
            raise ValueError(f"measure table {table_number} column count changed")
        for cell, value in zip(cells, values, strict=True):
            set_cell_text(cell, value or "n.d.", missing=value is None)
        table.append(clone)
    prefix = f"table_{table_number}_r"
    for slot in ledger.expected:
        if slot.startswith(prefix):
            ledger.record(slot, removed=True)
    ledger.record(f"table_{table_number}_rows")


def render_measure_tables(source: Path, data: PieeData, output: Path, ledger: AnchorLedger) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    _replace_rows(root, 367, tuple(_audit_row(row) for row in data.anexa.audit_measures), ledger)
    _replace_rows(
        root, 374, tuple(_solution_row(row) for row in data.anexa.existing_measures), ledger
    )
    _replace_rows(
        root, 395, tuple(_solution_row(row) for row in data.anexa.planned_measures), ledger
    )
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
