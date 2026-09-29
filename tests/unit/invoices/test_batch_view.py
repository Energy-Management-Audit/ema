"""Synthetic batch projection with evidence and workbook value parity."""

from __future__ import annotations

import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.workspace_jobs import create_job

from ema.api import create_app
from ema.api.invoice_models import InvoiceRow
from ema.api.mock import preview_pdf
from ema.core.errors import EmaError
from ema.core.jobs import StageOutcome, run_stage, subscribe
from ema.core.review.evidence import get_evidence
from ema.core.workspace import Workspace
from ema.invoices.artifact import decode_draft
from ema.invoices.batch_view import batch_view
from ema.invoices.export.workbook_contract import summary_net_value, summary_value_formula
from ema.invoices.identity_review import batch_client
from ema.invoices.identity_view import identity_view


def _field(value: str | None, label: str) -> dict[str, object]:
    return {
        "value": value,
        "status": "extracted" if value else "missing",
        "message": None,
        "evidence": [{"page_number": 1, "snippet": f"{label}: {value}", "label": label}]
        if value
        else [],
    }


def _draft(index: int, month: str, amount: int, pod: str | None) -> dict[str, object]:
    fields = {
        "client_name": _field("EXEMPLU ENERGIE SA", "Client"),
        "client_tax_id": _field("RO1234567", "CUI"),
        "location_identifier": _field(pod, "POD"),
        "invoice_number": _field(f"F{index}", "Factura"),
        "invoice_date": _field(f"2026-{month}-28", "Data"),
        "consumption_period": _field(f"01.{month}.2026–28.{month}.2026", "Perioada"),
        "active_energy": _field(str(amount), "Consum"),
        "active_energy_price": _field("1", "Pret"),
    }
    return {
        "document_id": f"draft-{index}",
        "source_filename": "same.pdf",
        "supplier": "SYNTHETIC",
        "fields": fields,
        "issues": [],
        "metadata": {},
        "price_details": [
            {
                "category": "active_energy",
                "description": "Active energy",
                "source_quantity": str(amount),
                "source_unit": "kWh",
                "source_unit_price": "1",
                "normalized_quantity": str(amount),
                "normalized_unit": "kWh",
                "normalized_unit_price": "1",
                "net_value": str(amount),
                "evidence": {"page_number": 1, "snippet": f"Consum: {amount}", "label": None},
            }
        ],
    }


def _outcome(index: int, month: str, amount: int, pod: str | None) -> dict[str, object]:
    return {
        "source_path": "same.pdf",
        "status": "exportable",
        "reason": None,
        "issues": [],
        "metadata": {},
        "drafts": [_draft(index, month, amount, pod)],
    }


def _synthetic_batch(tmp_path: Path) -> tuple[Workspace, str, list[str]]:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "synthetic", 2026)
    rows = [
        _outcome(1, "01", 100, "POD123"),
        _outcome(2, "03", 150, None),
        _outcome(3, "04", 100, "POD123"),
        {
            "source_path": "broken.pdf",
            "status": "failed",
            "reason": "Scan unreadable.",
            "issues": [],
            "metadata": {},
            "drafts": [],
        },
    ]
    shas: list[str] = []
    for index, row in enumerate(rows, 1):
        source = tmp_path / f"source-{index}.pdf"
        pdf = preview_pdf()
        if index == 1:
            pdf = pdf.replace(b"Synthetic preview", b"Consum: 100 kWh  ")
        source.write_bytes(pdf + f"\n% {index}".encode())
        sha = ws.add_file("synthetic", source)
        shas.append(sha)
        slot = f"invoices/{index:04d}"
        ws.set_slot(job, slot, sha, origin=str(row["source_path"]))
        row["slot"], row["file_sha"] = slot, sha

    def stage(ctx):  # type: ignore[no-untyped-def]
        ctx.read_slots("invoices")
        (ctx.artifact_dir() / "outcomes.json").write_text(json.dumps(rows), encoding="utf-8")
        return StageOutcome()

    run_stage(ws, job, "invoices", stage)
    for _event in subscribe(ws, job):
        pass
    return ws, job, shas


def test_batch_view_and_same_name_evidence(tmp_path: Path) -> None:
    ws, job, shas = _synthetic_batch(tmp_path)
    field, proposal = batch_client(ws, job)
    assert proposal is not None
    assert {get_evidence(ws, evidence_id).file_sha for evidence_id in field.evidence} == set(
        shas[:3]
    )
    identity = identity_view(ws, job)
    assert identity["revision"] == field.revision
    assert identity["reasons"] == {"printed": 3, "pods": ["POD123"], "other_client": 0}
    assert identity["pod_fill"] == [{"pod": "POD123", "files": ["same.pdf"], "source_count": 2}]
    assert identity["memory"] == []
    view = batch_view(ws, job)
    assert [row["slot"] for row in view["rows"]] == [
        "invoices/0001",
        "invoices/0002",
        "invoices/0003",
    ]
    assert len({row["id"] for row in view["rows"]}) == 3
    assert view["missing_months"] == ["2026-02"]
    assert view["year"] == 2026
    assert view["totals"]["months"] == 3
    assert view["totals"]["consumption_kwh"] == Decimal(350)
    assert view["totals"]["value_lei"] == Decimal(350)
    assert view["rows"][1]["outlier"] == {
        "ratio": Decimal("1.5"),
        "neighbours_mean_kwh": Decimal(100),
    }
    assert view["rows"][0]["sources"]["active_energy"] == {"page": 1, "snippet": "Consum: 100"}
    assert view["files"] == [
        {
            "slot": "invoices/0004",
            "file_name": "broken.pdf",
            "status": "failed",
            "reason": "Scan unreadable.",
        }
    ]
    assert view["read_ended_at"] is not None


def test_wire_decimals_and_stale_slot_snapshot(tmp_path: Path) -> None:
    ws, job, _shas = _synthetic_batch(tmp_path)
    view = batch_view(ws, job)
    high_precision = Decimal("12345678901234567890.123456")
    assert InvoiceRow.model_validate(
        {**view["rows"][0], "consumption_kwh": high_precision}
    ).model_dump(mode="json")["consumption_kwh"] == str(high_precision)
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"), base_url="http://127.0.0.1:8766"
    )
    client.post("/session", json={"code": "synthetic-code"})
    response = client.get(f"/jobs/{job}/invoices")
    assert response.status_code == 200
    wire = response.json()
    for key in ("consumption_kwh", "value_lei", "price_lei_kwh"):
        assert isinstance(wire["rows"][0][key], str)
    assert all(
        isinstance(wire["totals"][key], str)
        for key in ("consumption_kwh", "value_lei", "price_avg_lei_kwh")
    )
    full = client.get(f"/jobs/{job}/invoices/page.png?slot=invoices/0001&page=1")
    crop = client.get(f"/jobs/{job}/invoices/page.png?slot=invoices/0001&page=1&crop=active_energy")
    assert crop.status_code == 200
    assert Image.open(BytesIO(crop.content)).width < Image.open(BytesIO(full.content)).width
    replacement = tmp_path / "replacement.pdf"
    replacement.write_bytes(preview_pdf() + b"\n% replaced")
    ws.set_slot(job, "invoices/0001", ws.add_file("synthetic", replacement), origin="same.pdf")
    with pytest.raises(EmaError) as stale:
        batch_view(ws, job)
    assert stale.value.code == "invoices_stale"
    with pytest.raises(EmaError) as stale_identity:
        identity_view(ws, job)
    assert stale_identity.value.code == "invoices_stale"


def test_numeric_value_and_workbook_formula_share_category_filter() -> None:
    draft = _draft(1, "01", 100, "POD123")
    extra = dict(draft["price_details"][0])  # type: ignore[index]
    extra["category"] = "green_certificates"
    extra["net_value"] = "900"
    draft["price_details"] = [draft["price_details"][0], extra]  # type: ignore[index]
    invoice = decode_draft(draft)
    assert summary_net_value(invoice, "active_energy") == Decimal(100)
    assert summary_net_value(invoice, "green_certificates") == Decimal(900)
    assert '"active_energy"' in summary_value_formula("active_energy", 3, "R2")
    assert '"green_certificates"' in summary_value_formula("green_certificates", 3, "R2")
