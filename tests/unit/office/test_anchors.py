"""Synthetic checks for the shared Word anchor contract."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document
from docx.oxml.ns import qn

from ema.core.office.anchors import AnchorLedger, find, leftover_issues, stamp, strip


def test_bookmark_lookup_ledger_and_export_strip() -> None:
    document = Document()
    paragraph = document.add_paragraph("[de completat]")
    stamp(paragraph._p, "ch2_company", 42)
    roots = [document.element]
    assert find(roots, "ch2_company") is paragraph._p
    with pytest.raises(ValueError, match="found 0"):
        find(roots, "missing")
    ledger = AnchorLedger(frozenset({"ch2_company", "ch3_process"}))
    ledger.record("ch2_company")
    assert ledger.untouched == {"ch3_process"}
    ledger.record("ch3_process", removed=True)
    assert not ledger.untouched
    assert strip(roots) == 2
    assert not list(document.element.iter(qn("w:bookmarkStart")))
    assert paragraph.text == "[de completat]"


def _workbook_with_identity() -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", "<sst>ACME_PRIVATE</sst>")
    return stream.getvalue()


def test_leftover_check_covers_package_surfaces(tmp_path: Path) -> None:
    path = tmp_path / "synthetic.docx"
    with ZipFile(path, "w") as archive:
        archive.writestr("word/header1.xml", "<hdr>ACME_PRIVATE</hdr>")
        archive.writestr("word/charts/chart1.xml", "<chart>ACME_PRIVATE</chart>")
        archive.writestr("word/embeddings/data.xlsx", _workbook_with_identity())
        archive.writestr("docProps/core.xml", "<core>ACME_PRIVATE</core>")
        archive.writestr("word/document.xml", '<doc descr="ACME_PRIVATE"/>')
        archive.writestr(
            "word/_rels/document.xml.rels", '<rels><rel Target="https://ACME_PRIVATE.test"/></rels>'
        )
    assert set(leftover_issues(path, ("ACME_PRIVATE",))) == {
        "word/header1.xml",
        "word/charts/chart1.xml",
        "word/embeddings/data.xlsx",
        "docProps/core.xml",
        "word/document.xml",
        "word/_rels/document.xml.rels",
    }
    with pytest.raises(ValueError, match="denylist"):
        leftover_issues(path, ())
