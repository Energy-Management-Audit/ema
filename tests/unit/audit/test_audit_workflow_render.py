"""AuditWorkflow.render, the readiness snapshot and the export of an audit final (Word faked)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.unit.audit.render_seams import (
    FakeWord,
    fill_writer,
    outputs,
    synthetic_render,
    write_intros,
)

from ema.api import create_app
from ema.audit import render
from ema.audit.catalogue import CATALOGUE
from ema.audit.sections import Status, set_status
from ema.audit.workflow import AuditWorkflow
from ema.core.jobs import subscribe
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def _session(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(ws, 8766, launch_code="synthetic-code"), base_url=BASE)
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    return client, {"X-Ema-CSRF": token}


def _start(client: TestClient, headers: dict[str, str], job: str, stage: str) -> object:
    revision = client.get(f"/jobs/{job}").json()["revision"]
    return client.post(
        f"/jobs/{job}/stages/{stage}", json={"on_revision": revision}, headers=headers
    )


@pytest.fixture
def ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Workspace, str]:
    """Every section n/a for readiness, the report's markers written, Word present."""
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    write_intros(ws, job)
    for section in CATALOGUE:
        set_status(ws, job, section.id, Status.NA, "user")
    monkeypatch.setattr(render, "_statuses", lambda ws, job: {"ch4.bilant_real": Status.NA})
    monkeypatch.setattr(render, "write_draft", fill_writer("ch2.date_generale", "ch3.flux"))
    monkeypatch.setattr(render, "word_available", lambda settings: True)
    monkeypatch.setattr(render, "word_automation", lambda settings: FakeWord())
    return ws, job


def test_render_draft_waits_and_a_new_draft_changes_the_snapshot(
    ready: tuple[Workspace, str],
) -> None:
    ws, job = ready
    workflow = AuditWorkflow()
    before = workflow.readiness_snapshot(ws, job)
    assert before["render"] is None
    first = workflow.render(ws, job, "draft")
    snapshot = workflow.readiness_snapshot(ws, job)
    assert snapshot["render"] is not None and snapshot != before
    second = workflow.render(ws, job, "draft")
    assert second != first
    assert workflow.readiness_snapshot(ws, job) != snapshot
    names = [name for name, _ in outputs(ws, job)]
    assert names == ["Audit-ciorna.pdf", "Audit-ciorna.docx"] * 2


def test_final_through_the_stage_route_and_export(ready: tuple[Workspace, str]) -> None:
    ws, job = ready
    client, headers = _session(ws)
    started = _start(client, headers, job, "audit_final")
    assert started.status_code == 202, started.json()
    assert started.json()["stage"] == "audit_final"
    list(subscribe(ws, job))
    final_id = AuditWorkflow().render(ws, job, "final")
    listed = {item["id"]: item for item in client.get(f"/jobs/{job}/outputs").json()}
    assert (listed[final_id]["kind"], listed[final_id]["name"]) == ("final", "Audit-final.docx")
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert checks["readiness"]["final_ok"]
    exported = client.post(
        f"/jobs/{job}/export",
        json={
            "final": True,
            "output_id": final_id,
            "readiness_hash": checks["readiness_hash"],
            "confirm": True,
        },
        headers=headers,
    )
    assert exported.status_code == 200, exported.json()
    approvals = client.get(f"/jobs/{job}/approvals").json()
    assert [(item["output_id"], item["readiness_hash"]) for item in approvals] == [
        (final_id, checks["readiness_hash"])
    ]
    copy = ws.root / "exports" / f"{job}-{final_id}.docx"
    final_bytes = client.get(f"/jobs/{job}/outputs/{final_id}").content
    assert copy.read_bytes() == final_bytes


def test_final_is_refused_before_readiness_and_without_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    client, headers = _session(ws)
    refused = _start(client, headers, job, "audit_final")
    assert refused.status_code == 409
    assert refused.json()["type"] == "urn:ema:error:not_ready"
    for section in CATALOGUE:
        set_status(ws, job, section.id, Status.NA, "user")
    no_word = _start(client, headers, job, "audit_final")
    assert no_word.status_code == 424
    assert no_word.json() == {
        "type": "urn:ema:error:word_unavailable",
        "title": "Microsoft Word nu este disponibil.",
        "status": 424,
    }
    draft = _start(client, headers, job, "audit_render")
    assert draft.status_code == 202
    list(subscribe(ws, job))
    monkeypatch.delenv("EMA_AUDIT_BASE_DOCUMENT")
    missing = _start(client, headers, job, "audit_render")
    assert missing.status_code == 409
    assert missing.json()["title"] == "Baza auditului nu este configurată."
