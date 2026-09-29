"""The reviewed local PIEE base map covers client and numeric contract surfaces."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx.oxml.ns import qn

from ema.core.office.base_map import load, validate
from ema.core.office.package import read_parts, xml
from ema.piee.base import SUPPORTED_BASE_SHA, build_local_base

pytestmark = pytest.mark.golden


def test_invoice_case_e_base_map_is_complete_and_version_bound(
    reference_library: Path, tmp_path: Path
) -> None:
    bases = list((reference_library / "piee" / "finished-programs").glob("*MODEL_2026.docx"))
    assert len(bases) == 1
    mapping = build_local_base(bases[0], tmp_path)
    assert mapping.base_sha == SUPPORTED_BASE_SHA
    assert len(mapping.elements) == 1695
    assert len(mapping.variable_slots) == 613
    body = xml(read_parts(bases[0]), "word/document.xml").find(qn("w:body"))
    assert body is not None
    for index in (5, 415, 416, 417):
        path = list(body)[index - 1].getroottree().getelementpath(list(body)[index - 1])
        assert (
            next(
                item.classification
                for item in mapping.elements
                if item.id == f"paragraph:word/document.xml:{path}"
            )
            == "fixed"
        )
    validate(bases[0], load(tmp_path / "base-map.json"))
    assert (tmp_path / "piee-master.docx").is_file()
    assert (tmp_path / "piee-preview.docx").is_file()
    assert (tmp_path / "base-identity.json").is_file()
    assert (tmp_path / "identity-spans.json").is_file()
    assert (tmp_path / "section-groups.json").is_file()
