"""Batch confirmation, memory and contradictory printed identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ema.clients import find_by_pod
from ema.core.config import Settings
from ema.core.errors import EmaError
from ema.core.jobs import StageOutcome, create_job, run_stage, subscribe
from ema.core.workspace import Workspace
from ema.invoices.composition import build_invoice_processor
from ema.invoices.identity_review import (
    batch_client,
    confirm_client,
    readiness,
    resolved_outcomes,
    undo_client,
)
from ema.invoices.models import DocumentPage, InputDocument, IssueCode, TextBlock
from ema.invoices.parsers.alive_identity import buyer_fields
from ema.invoices.parsers.alive_parser import AliveInvoiceParser
from ema.invoices.parsers.alive_prices import price_details


def _field(value: str | None, status: str, *, snippet: str = "") -> dict:
    return {
        "value": value,
        "status": status,
        "message": None,
        "evidence": ([{"page_number": 1, "snippet": snippet, "label": None}] if snippet else []),
    }


def _row(
    file: str, name: str | None, pod: str | None, tax: str | None = None, *, ambiguous: bool = False
) -> dict:
    name_field = _field(
        name,
        "ambiguous" if ambiguous else "extracted" if name else "missing",
        snippet="Nume client: ALPHA SRL" if ambiguous else f"Client: {name}" if name else "",
    )
    fields = {
        "client_name": name_field,
        "client_tax_id": _field(
            tax, "extracted" if tax else "not_provided", snippet=f"CUI: {tax}" if tax else ""
        ),
        "location_identifier": _field(
            pod, "extracted" if pod else "missing", snippet=f"POD: {pod}" if pod else ""
        ),
    }
    issues = [
        {
            "field_id": key,
            "severity": "error",
            "message": "needs review",
            "code": "MISSING_CLIENT_IDENTITY",
        }
        for key, value in fields.items()
        if value["status"] in {"missing", "ambiguous"}
    ]
    return {
        "source_path": file,
        "status": "requires_review" if issues else "exportable",
        "issues": [],
        "reason": None,
        "metadata": {},
        "drafts": [
            {
                "supplier": "SUPPLIER",
                "source_filename": file,
                "fields": fields,
                "issues": issues,
                "metadata": {},
            }
        ],
    }


def _job(ws: Workspace, tmp_path: Path, rows: list[dict]) -> str:
    job = create_job(ws, "invoices", "example", None)
    for index, row in enumerate(rows, 1):
        path = tmp_path / row["source_path"]
        path.write_bytes(b"synthetic PDF content")
        sha = ws.add_file("example", path)
        ws.set_slot(job, f"invoices/{index:04d}", sha, origin=path.name)

    def stage(ctx):  # type: ignore[no-untyped-def]
        ctx.read_slots("invoices")
        (ctx.artifact_dir() / "outcomes.json").write_text(json.dumps(rows))
        return StageOutcome()

    run_stage(ws, job, "invoices", stage)
    for _ in subscribe(ws, job):
        pass
    return job


def test_one_confirmation_fills_missing_and_ambiguous_but_keeps_contradiction(
    tmp_path: Path,
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(
        ws,
        tmp_path,
        [
            _row("a.pdf", "ALPHA", "POD0001", "RO123", ambiguous=True),
            _row("b.pdf", None, None),
            _row("c.pdf", "BETA SA", "POD0001"),
        ],
    )
    field, proposed = batch_client(ws, job)
    assert field.review == "pending" and proposed is not None
    assert proposed.name == "ALPHA SRL"
    assert proposed.pod_fill[0]["files"] == ["b.pdf"]
    assert proposed.disagreements == ("c.pdf",)
    assert not readiness(ws, job).final_ok

    decision = confirm_client(ws, job)
    rows = resolved_outcomes(ws, job)
    assert [row["status"] for row in rows] == ["exportable", "exportable", "requires_review"]
    filled = rows[1]["drafts"][0]
    assert filled["fields"]["location_identifier"]["value"] == "POD0001"
    assert filled["metadata"]["pod_confirmation_decision"] == decision.id
    assert len(filled["fields"]["location_identifier"]["evidence"]) == 2
    assert readiness(ws, job).exportable == 2

    remembered_job = _job(ws, tmp_path, [_row("next.pdf", None, "POD0001")])
    _, memory_proposal = batch_client(ws, remembered_job)
    assert memory_proposal is not None and memory_proposal.memory
    assert memory_proposal.name == "ALPHA SRL"

    undo_client(ws, job, decision.id)
    assert not readiness(ws, job).final_ok
    forgotten_job = _job(ws, tmp_path, [_row("later.pdf", None, "POD0001")])
    assert batch_client(ws, forgotten_job)[1] is None


def test_known_pod_with_different_cui_conflicts(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws, tmp_path, [_row("a.pdf", "ALPHA SRL", "POD0001", "RO123")])
    confirm_client(ws, job)
    conflict = _job(ws, tmp_path, [_row("b.pdf", "BETA SA", "POD0001", "RO456")])
    with pytest.raises(EmaError) as error:
        batch_client(ws, conflict)
    assert error.value.code == "client_memory_conflict"
    ws.delete_job(job)
    assert not find_by_pod(ws, "POD0001")


def test_known_cui_proposes_client_without_pod(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    first = _job(ws, tmp_path, [_row("a.pdf", "ALPHA SRL", "POD0001", "RO123")])
    confirm_client(ws, first)
    next_job = _job(ws, tmp_path, [_row("b.pdf", None, None, "123")])
    field, proposed = batch_client(ws, next_job)
    assert field.review == "pending"
    assert proposed is not None and proposed.name == "ALPHA SRL"
    assert {item["kind"] for item in proposed.memory} == {"cui"}


def test_ambiguous_candidate_prefix_does_not_confirm_another_company(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    other = _row("b.pdf", "ALPHA SRL GROUP", "POD0001", ambiguous=True)
    other["drafts"][0]["fields"]["client_name"]["evidence"][0]["snippet"] = (
        "Nume client: ALPHA SRL GROUP"
    )
    job = _job(ws, tmp_path, [_row("a.pdf", "ALPHA SRL", "POD0001"), other])
    confirm_client(ws, job)
    assert resolved_outcomes(ws, job)[1]["status"] == "requires_review"


def test_new_extraction_requires_new_batch_confirmation(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws, tmp_path, [_row("a.pdf", "ALPHA SRL", "POD0001")])
    confirm_client(ws, job)
    assert readiness(ws, job).final_ok

    def stage(ctx):  # type: ignore[no-untyped-def]
        ctx.read_slots("invoices")
        (ctx.artifact_dir() / "outcomes.json").write_text(
            json.dumps([_row("a.pdf", "ALPHA SRL", "POD0001")])
        )
        return StageOutcome()

    run_stage(ws, job, "invoices", stage)
    for _ in subscribe(ws, job):
        pass
    assert not readiness(ws, job).final_ok
    assert batch_client(ws, job)[0].review == "pending"


def test_alive_buyer_column_uses_client_cui_not_supplier_cui() -> None:
    blocks = (
        TextBlock("CIF:", 30, 120, 45, 130),
        TextBlock("RO111111", 48, 120, 90, 130),
        TextBlock("Client", 320, 100, 355, 110),
        TextBlock("ALPHA", 320, 120, 360, 130),
        TextBlock("SRL", 365, 120, 385, 130),
        TextBlock("CIF:", 320, 140, 345, 150),
        TextBlock("RO222222", 348, 140, 398, 150),
    )
    document = InputDocument(
        Path("alive.pdf"), (DocumentPage(1, "ALIVE CAPITAL FACTURA", blocks, "ocr"),)
    )
    fields = buyer_fields(document)
    assert fields["client_name"].value == "ALPHA SRL"
    assert fields["client_tax_id"].value == "RO222222"


def test_alive_meter_zero_ocr_variant() -> None:
    page = DocumentPage(
        1,
        "Energie reactiva capacitiva ERC 1 - 30 aprilie 2024 123456 16000 5.437 5.437 [9] kVArh",
        (),
        "ocr",
    )
    details = price_details(InputDocument(Path("alive.pdf"), (page,)))
    assert len(details) == 1
    assert details[0].source_quantity == 0


def test_alive_printed_position_count_excludes_unbilled_meter_readings() -> None:
    page = DocumentPage(
        1,
        "Nr. pozitii fact.: 2\n"
        "1 Energie electrica activa livrata MWh 2.000 10.00 20.00 3.80\n"
        "2 Tarif injectie MWh 2.000 3.00 6.00 1.14\n"
        "Energie reactiva capacitiva ERC 1 - 30 aprilie 2024 123456 16000 5.437 5.437 0 kVArh",
        (),
        "ocr",
    )
    draft = AliveInvoiceParser().parse(InputDocument(Path("alive.pdf"), (page,)))[0]
    assert draft.metadata["printed_position_count"] == 2
    assert draft.metadata["parsed_position_count"] == 2
    assert IssueCode.INVOICE_POSITION_COUNT_MISMATCH not in {issue.code for issue in draft.issues}

    mismatch = DocumentPage(1, page.text.replace("fact.: 2", "fact.: 3"), (), "ocr")
    rejected = AliveInvoiceParser().parse(InputDocument(Path("alive.pdf"), (mismatch,)))[0]
    assert IssueCode.INVOICE_POSITION_COUNT_MISMATCH in {issue.code for issue in rejected.issues}


def test_alive_ocr_timeout_fails_only_that_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = [tmp_path / "timeout.pdf", tmp_path / "other.pdf"]
    for index, path in enumerate(files):
        path.write_bytes(f"synthetic-{index}".encode())
    processor = build_invoice_processor(Settings())

    def read(path: Path) -> InputDocument:
        if path.name == "timeout.pdf":
            raise EmaError("ocr_timeout", "OCR-ul a depășit timpul permis.", "synthetic")
        return InputDocument(path, (DocumentPage(1, "ALIVE CAPITAL factura", (), "ocr"),))

    monkeypatch.setattr(processor._reader, "read", read)
    result = processor.execute(files)
    assert result.outcomes[0].status == "failed"
    assert IssueCode.OCR_TIMEOUT in result.outcomes[0].issue_codes
    assert "ocr_timeout" in (result.outcomes[0].metadata.technical_detail or "")
    assert result.outcomes[1].status == "requires_review"
