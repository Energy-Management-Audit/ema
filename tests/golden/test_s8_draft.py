"""Partial PIEE drafts surface unmapped content without leaking the base identity."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from docx.oxml.ns import qn

from ema.core.office.package import read_parts, xml
from ema.piee.compose import compose_draft
from ema.piee.dataset import load


@pytest.mark.golden
@pytest.mark.parametrize("case_name", ["piee-case-a", "piee-case-b"])
def test_draft_is_standalone_and_marks_remaining_fields(tmp_path: Path, case_name: str) -> None:
    reference = os.environ.get("EMA_REFERENCE")
    if reference is None:
        pytest.fail("EMA_REFERENCE is required for the S8 golden")
    case = Path(reference) / "piee/cases" / case_name
    anexa = next(case.rglob("Anexa*.xlsx"))
    necesar = next(case.rglob("Necesar*.xls"), None)
    prelucrare = next(case.rglob("*Prelucrare*.xls*"))
    data = load(2025, anexa, necesar, prelucrare)
    output = tmp_path / "draft.docx"

    result = compose_draft(data, Path.home() / "Ema-dev/s8/base", output, date(2026, 9, 24))

    assert result.package_issues == ()
    assert result.leftover_parts == ()
    assert result.untouched
    assert not result.final_ready
    root = xml(read_parts(output), "word/document.xml")
    assert any(node.get(qn("w:val")) == "FF0000" for node in root.iter(qn("w:color")))
    assert not any(
        (node.get(qn("w:name")) or "").startswith("_ema_")
        for node in root.iter(qn("w:bookmarkStart"))
    )
