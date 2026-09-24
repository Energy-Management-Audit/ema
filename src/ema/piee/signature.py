"""Fill the authored signature cells without changing their table styling."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path

from docx.oxml.ns import qn

from ema.core.office.anchor_targets import find_cell, find_row
from ema.core.office.anchors import AnchorLedger
from ema.core.office.cell_text import set_paragraph_text
from ema.core.office.package import encoded, read_parts, write_parts, xml


def render_signature(
    source: Path,
    values: dict[str, str | None],
    output: Path,
    ledger: AnchorLedger,
) -> None:
    parts = read_parts(source)
    root = xml(parts, "word/document.xml")
    row = find_row([root], "table_420_rows")
    if len(row.findall(qn("w:tc"))) != 3:
        raise ValueError("signature table structure changed")
    client = find_cell([root], "table_420_r0_c0")
    contact = find_cell([root], "table_420_r0_c1")
    dated = find_cell([root], "table_420_r0_c2")
    if tuple(len(cell.findall(qn("w:p"))) for cell in (client, contact, dated)) != (4, 5, 3):
        raise ValueError("signature cell structure changed")
    name = values.get("client_name")
    set_paragraph_text(client.findall(qn("w:p"))[0], name or "n.d.", missing=name is None)
    person = values.get("contact_person")
    set_paragraph_text(contact.findall(qn("w:p"))[3], person or "n.d.", missing=person is None)
    set_paragraph_text(contact.findall(qn("w:p"))[4], "")
    generation_date = values.get("generation_date")
    set_paragraph_text(
        dated.findall(qn("w:p"))[2],
        generation_date or "n.d.",
        missing=generation_date is None,
    )
    for slot in ("table_420_rows", "table_420_r0_c0", "table_420_r0_c1", "table_420_r0_c2"):
        ledger.record(slot)
    parts["word/document.xml"] = encoded(root)
    write_parts(parts, output)
