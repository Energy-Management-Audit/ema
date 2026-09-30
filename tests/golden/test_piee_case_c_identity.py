"""The two-site source declaration and missing address survive PIEE identity rendering."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from docx import Document
from tests.golden.cases import case_path
from tests.unit.piee.synthetic_piee import piee_data
from tests.workspace_jobs import create_job

from conftest import artifacts_path
from ema.core.office.anchors import AnchorLedger
from ema.core.review import fields
from ema.core.workspace import Workspace
from ema.energy_data.anexa import parse_anexa
from ema.piee.compose import load_approved_base
from ema.piee.identity import identity_values
from ema.piee.identity_map import render_identity
from ema.piee.intake import _record_identity
from ema.piee.review_workflow import PieeWorkflow

pytestmark = pytest.mark.golden


def test_piee_case_c_two_site_identity_keeps_distinct_evidence(tmp_path: Path) -> None:
    anexa = parse_anexa(case_path("piee-case-c", "anexa"))
    identity = anexa.identity
    assert identity["site_1_name"].ref.a1 == "Date generale!C2"
    assert identity["site_2_name"].ref.a1 == "Date generale!C2"
    assert identity["name"].ref.a1 == "Date generale!C2"
    assert "sucursalele" not in str(identity["name"].value).lower()
    assert identity["site_1_address"].ref.a1 == "Date generale!C3"
    assert "site_2_address" not in identity
    assert anexa.audit["boundary"].ref.a1 == "Audit energetic!C4"
    assert "total_tep" in anexa.annual
    assert not any(key.startswith("site_") for key in anexa.annual)
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "piee-case-c", 2026)
    _record_identity(ws, job, replace(piee_data(), anexa=anexa), "case-c-sha")
    by_key = {field.key: field for field in fields(ws, job)}
    for key in ("site_1_name", "site_2_name", "site_1_address"):
        assert by_key[f"identity.{key}"].presence == "found"
    for key in (
        "site_2_address",
        "site_1_production_share",
        "site_2_production_share",
    ):
        assert by_key[f"identity.{key}"].presence == "not_found"
        assert not by_key[f"identity.{key}"].required
    assert len(PieeWorkflow().readiness(ws, job).warnings) == 3

    base = artifacts_path("s8", "base")
    mapping = load_approved_base(base)
    output = tmp_path / "identity.docx"
    render_identity(
        base / "piee-master.docx",
        base / "identity-spans.json",
        identity_values(anexa, date(2026, 9, 30), analysis_year=2025),
        output,
        AnchorLedger(mapping.variable_slots),
        mapping,
    )
    paragraphs = Document(output).paragraphs
    first = f"- Sucursala {identity['site_1_name'].value}: {identity['site_1_address'].value};"
    second = f"- Sucursala {identity['site_2_name'].value}: n.d."
    assert first in [paragraph.text for paragraph in paragraphs]
    line = next(paragraph for paragraph in paragraphs if paragraph.text == second)
    assert [
        run.text for run in line.runs if run.font.color and str(run.font.color.rgb) == "FF0000"
    ] == ["n.d."]
    split = next(
        paragraph
        for paragraph in paragraphs
        if paragraph.text.startswith("Din totalul producției pe anul 2025,")
    )
    assert split.text == (
        f"Din totalul producției pe anul 2025, sucursala {identity['site_1_name'].value} "
        f"are un procent de n.d.% iar sucursala {identity['site_2_name'].value} n.d.%."
    )
    assert [
        run.text for run in split.runs if run.font.color and str(run.font.color.rgb) == "FF0000"
    ] == ["n.d.", "n.d."]
    assert (
        len(
            [
                paragraph
                for paragraph in paragraphs
                if str(identity["site_2_name"].value) in paragraph.text
            ]
        )
        == 2
    )
    assert [
        paragraph.text
        for paragraph in paragraphs
        if str(identity["site_1_name"].value) in paragraph.text
    ] == [first, split.text]
