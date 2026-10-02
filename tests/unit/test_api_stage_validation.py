"""Stage dispatch rejects unsupported or unsafe requests before starting work."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.workspace_jobs import create_job

from ema import invoices, workflows_registry
from ema.api import create_app
from ema.api.job_routes import start_named_stage
from ema.audit import stages as audit_stages
from ema.clients.registry import create_client
from ema.core.errors import EmaError
from ema.core.workspace import Workspace


@pytest.mark.parametrize(
    ("job_type", "stage", "human_session", "code"),
    [
        ("audit", "missing", False, "invalid_stage"),
        ("audit", "draft", False, "ai_client_disabled"),
        ("invoices", "invoices_workbook", False, "human_required"),
        ("invoices", "invoices", False, "not_ready"),
        ("piee", "intake", False, "invalid_stage"),
    ],
)
def test_stage_dispatch_rejects_before_work(
    tmp_path: Path,
    job_type: str,
    stage: str,
    human_session: bool,
    code: str,
) -> None:
    ws = Workspace(tmp_path)
    client_id = create_client(ws, "Synthetic")["id"]
    job = create_job(ws, job_type, client_id, 2026)  # type: ignore[arg-type]

    with pytest.raises(EmaError) as rejected:
        start_named_stage(ws, job, stage, 1, human_session=human_session)

    assert rejected.value.code == code


def test_stage_dispatch_checks_revision_and_running_state(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    client_id = create_client(ws, "Synthetic")["id"]
    job = create_job(ws, "audit", client_id, 2026)

    with pytest.raises(EmaError) as stale:
        start_named_stage(ws, job, "intake", 99)
    assert stale.value.code == "stale_revision"

    with ws.connect() as db:
        db.execute("UPDATE jobs SET state='running' WHERE id=?", (job,))
    with pytest.raises(EmaError) as running:
        start_named_stage(ws, job, "intake", 1)
    assert running.value.code == "job_running"


def test_stage_dispatch_rejects_missing_and_deleted_jobs(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    with pytest.raises(EmaError) as missing:
        start_named_stage(ws, "absent", "intake", 0)
    assert missing.value.code == "job_missing"

    client_id = create_client(ws, "Synthetic")["id"]
    job = create_job(ws, "audit", client_id, 2026)
    with ws.connect() as db:
        db.execute("UPDATE jobs SET deleted=1 WHERE id=?", (job,))
    with pytest.raises(EmaError) as deleted:
        start_named_stage(ws, job, "intake", 1)
    assert deleted.value.code == "job_missing"


@pytest.mark.parametrize(
    ("job_type", "stage", "runner"),
    [
        ("audit", "intake", "run_stage"),
        ("audit", "read", "run_stage"),
        ("piee", "piee_generate", "start_generate_for_job"),
        ("piee", "piee_word", "start_word_render"),
        ("invoices", "invoices", "run_stage"),
        ("invoices", "invoices_workbook", "start_workbook"),
    ],
)
def test_stage_dispatch_starts_supported_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    job_type: str,
    stage: str,
    runner: str,
) -> None:
    ws = Workspace(tmp_path)
    client_id = create_client(ws, "Synthetic")["id"]
    job = create_job(ws, job_type, client_id, 2026)  # type: ignore[arg-type]
    calls: list[tuple[Any, ...]] = []

    def fake_runner(*args: Any, **kwargs: Any) -> str:
        calls.append((*args, kwargs))
        return "synthetic-run"

    module = (
        audit_stages
        if job_type == "audit"
        else invoices
        if job_type == "invoices" and stage == "invoices"
        else workflows_registry
    )
    monkeypatch.setattr(module, runner, fake_runner)
    monkeypatch.setattr(audit_stages, "select_checklist", lambda _slots: None)
    monkeypatch.setattr(ws, "list_slots", lambda *_args: ["invoices/2026"])

    assert start_named_stage(ws, job, stage, 1, human_session=True) == "synthetic-run"
    assert calls


def test_piee_routes_render_only_supported_draft_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path)
    client_id = create_client(ws, "Synthetic")["id"]
    piee = create_job(ws, "piee", client_id, 2026)
    invoice = create_job(ws, "invoices", client_id, 2026)
    audit = create_job(ws, "audit", client_id, 2026)
    reporting = create_job(ws, "reporting", client_id, 2026)
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"), base_url="http://127.0.0.1:8766"
    )
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    headers = {"X-Ema-CSRF": token}

    for job in (piee, invoice, audit, reporting):
        response = client.post(
            f"/jobs/{job}/export/draft", json={"on_revision": 1}, headers=headers
        )
        assert response.status_code == 404
