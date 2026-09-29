"""Synthetic Fill trust-boundary and section-state regressions."""

from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.audit.catalogue_types import MaterialKind
from ema.audit.fill_tools import FillDocument, FillTools
from ema.audit.sections import get_status, record_material
from ema.core.errors import EmaError
from ema.core.review.fields import fields, propose
from ema.core.review.models import Evidence, FieldSpec, PdfText
from ema.core.review.section_transition import Status
from ema.core.workspace import Workspace


def _tools(tmp_path: Path) -> tuple[FillTools, Workspace, str]:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "made-up", 2026)
    documents = {
        "fisa.txt": FillDocument("fisa.txt", "Firma Exemplu SRL are sediul în Alba."),
        "permit.pdf": FillDocument("permit.pdf", "Permis pentru Firma Exemplu SRL, 500 m²."),
    }
    return FillTools(ws, job, "ch2.date_generale", documents), ws, job


def test_verbatim_fact_and_missing_fact(tmp_path: Path) -> None:
    tools, ws, job = _tools(tmp_path)
    with pytest.raises(EmaError) as error:
        tools.record_fact(
            {
                "key": "audit.company_name",
                "value": "Firma Exemplu SRL",
                "name": "fisa.txt",
                "quote": "Firma Inventată SRL",
            }
        )
    assert error.value.code == "evidence_quote"
    recorded = tools.record_fact(
        {
            "key": "audit.company_name",
            "value": "Firma Exemplu SRL",
            "name": "fisa.txt",
            "quote": "Firma Exemplu SRL are sediul în Alba.",
        }
    )
    assert recorded["evidence"]
    tools.mark_missing({"key": "audit.cui"})
    found = {item.key: item for item in fields(ws, job)}
    assert found["audit.company_name"].presence == "found"
    assert found["audit.cui"].presence == "not_found"


def test_number_must_appear_in_quote(tmp_path: Path) -> None:
    tools, _, _ = _tools(tmp_path)
    with pytest.raises(EmaError) as error:
        tools.record_fact(
            {
                "key": "audit.employees",
                "value": 700,
                "name": "permit.pdf",
                "quote": "500 m²",
            }
        )
    assert error.value.code == "value_unverified"


def test_dataset_fact_refuses_missing_evidence_row(tmp_path: Path) -> None:
    tools, ws, job = _tools(tmp_path)
    evidence = tools._document_evidence("fisa.txt", "Firma Exemplu SRL", "Firma Exemplu SRL")
    propose(
        ws,
        job,
        FieldSpec(key="audit.company_name", label="Company", value_type="text"),
        "Firma Exemplu SRL",
        [evidence],
        state="supplied",
    )
    with ws.connect() as db:
        db.execute("DELETE FROM evidence WHERE job_id=? AND id=?", (job, evidence.id))
    with pytest.raises(EmaError) as error:
        tools.record_fact(
            {
                "key": "audit.company_name",
                "value": "Firma Exemplu SRL",
                "source_key": "audit.company_name",
            }
        )
    assert error.value.code == "evidence_missing"


def test_fact_must_belong_to_active_section(tmp_path: Path) -> None:
    tools, ws, job = _tools(tmp_path)
    with pytest.raises(EmaError) as error:
        tools.record_fact(
            {
                "key": "audit.business_activity",
                "value": "Alba",
                "name": "fisa.txt",
                "quote": "Firma Exemplu SRL are sediul în Alba.",
            }
        )
    assert error.value.code == "fact_section"
    assert not any(item.key == "audit.business_activity" for item in fields(ws, job))


def test_pdf_quote_keeps_its_real_page(tmp_path: Path) -> None:
    tools, ws, job = _tools(tmp_path)
    tools.documents["permit.pdf"] = FillDocument(
        "permit.pdf", "", page_texts=("Prima pagină.", "Sediu: Alba.")
    )
    result = tools.record_fact(
        {"key": "audit.address", "value": "Alba", "name": "permit.pdf", "quote": "Sediu: Alba."}
    )
    with ws.connect() as db:
        row = db.execute(
            "SELECT data FROM evidence WHERE job_id=? AND id=?", (job, result["evidence"][0])
        ).fetchone()
    assert row is not None
    evidence = Evidence.model_validate_json(row["data"])
    assert evidence.locator == PdfText(page=2, span="Sediu: Alba.")


def test_na_is_only_proposed_for_absent_trigger(tmp_path: Path) -> None:
    tools, ws, job = _tools(tmp_path)
    with pytest.raises(EmaError) as error:
        tools.propose_na({"reason": "No company"})
    assert error.value.code == "na_trigger"
    record_material(ws, job, MaterialKind.METER, False, "synthetic intake")
    electric = FillTools(ws, job, "ch5.electric", {})
    electric.propose_na({"reason": "No meter photos in synthetic dossier"})
    state = get_status(ws, job, "ch5.electric")
    assert state.status == Status.NA_PROPOSED
    assert state.na_applicable is False
    assert state.reason == "No meter photos in synthetic dossier"
