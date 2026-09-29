"""A final run is delivered as one retryable operation through API and CLI."""

import json
from pathlib import Path

import pytest
from tests.unit.audit.test_final_currency import approved
from tests.unit.test_s17b_clients_routes import _session
from typer.testing import CliRunner

from ema.api import export_routes
from ema.audit.workflow import AuditWorkflow
from ema.cli import _app
from ema.cli import review as cli_review
from ema.clients.registry import create_client
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, create_job, run_stage, subscribe
from ema.core.review import export_final, final_export, readiness_hash
from ema.core.review.models import Readiness
from ema.core.workspace import Workspace


class ReadyAudit(AuditWorkflow):
    def readiness(self, ws, job):
        return Readiness(draft_ok=True, final_ok=True)

    def readiness_in_tx(self, ws, job, db):
        return self.readiness(ws, job)

    def render(self, *_args):
        raise AssertionError("Export must use the final already reviewed")


def outputs(ws: Workspace, job: str, *, draft: bool = False) -> str:
    def stage(ctx: StageContext) -> StageOutcome:
        for name in ["draft.docx"] if draft else ["Audit.docx", "Audit.pdf", "Prelucrare.xlsx"]:
            source = ctx.artifact_dir() / name
            source.write_bytes(name.encode())
            ctx.save_output(source, name, kind="draft" if draft else "final")
        return StageOutcome()

    run = run_stage(ws, job, "audit_render" if draft else "audit_final", stage)
    list(subscribe(ws, job))
    with ws.connect() as db:
        return str(
            db.execute(
                "SELECT id FROM outputs WHERE run_id=? AND relative_path LIKE '%.docx'", (run,)
            ).fetchone()[0]
        )


def setup(tmp_path: Path):
    ws = Workspace(tmp_path / "workspace")
    person = create_client(ws, "Example", "12345678")
    job = create_job(ws, "audit", person["id"], 2026)
    output = outputs(ws, job)
    return ws, job, output, ReadyAudit()


def test_newer_draft_does_not_block_current_final_api_export(tmp_path, monkeypatch):
    ws, job, output, workflow = setup(tmp_path)
    outputs(ws, job, draft=True)
    monkeypatch.setattr(export_routes, "workflow_for", lambda *_: workflow)
    http, headers = _session(ws)
    checks = http.get(f"/jobs/{job}/export/checks").json()
    assert checks["final"]["output_id"] == output
    assert checks["final"]["created_at"]
    assert checks["final"]["files"] == ["Audit.docx", "Audit.pdf", "Prelucrare.xlsx"]
    body = {
        "output_id": output,
        "readiness_hash": checks["readiness_hash"],
        "confirm": True,
        "dest_dir": None,
    }
    response = http.post(f"/jobs/{job}/export", json=body, headers=headers)
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(result) == {"approved_at", "files", "folder"}
    assert Path(result["folder"]) == ws.root / "exports" / "Example Audit energetic 2026"
    for file in result["files"]:
        assert Path(file["path"]).read_bytes() == file["name"].encode()
    assert http.post(f"/jobs/{job}/export", json=body, headers=headers).json() == result
    with ws.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 1
        assert (
            db.execute("SELECT COUNT(*) FROM job_events WHERE type='exported'").fetchone()[0] == 1
        )


def test_copy_failure_keeps_approval_undelivered_and_same_request_retries(tmp_path, monkeypatch):
    ws, job, output, workflow = setup(tmp_path)
    digest = readiness_hash(ws, job, workflow.readiness(ws, job), workflow)
    original = final_export.copy_output

    def fail_pdf(ws, relative, sha, dest):
        if dest.suffix == ".pdf":
            raise PermissionError("synthetic copy failure")
        return original(ws, relative, sha, dest)

    monkeypatch.setattr(final_export, "copy_output", fail_pdf)
    with pytest.raises(EmaError) as error:
        export_final(ws, job, output, digest, tmp_path / "delivery", workflow=workflow)
    assert error.value.code == "output_copy_failed"
    with ws.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 1
        assert (
            db.execute("SELECT COUNT(*) FROM job_events WHERE type='exported'").fetchone()[0] == 0
        )
    http, _headers = _session(ws)
    failed = http.get(f"/jobs/{job}/approvals").json()
    assert len(failed) == 1 and failed[0]["exported_at"] is None
    approval_id = failed[0]["id"]
    monkeypatch.setattr(final_export, "copy_output", original)
    result = export_final(ws, job, output, digest, tmp_path / "delivery", workflow=workflow)
    assert [f.name for f in result.files] == ["Audit.docx", "Audit.pdf", "Prelucrare.xlsx"]
    delivered = http.get(f"/jobs/{job}/approvals").json()
    assert len(delivered) == 1 and delivered[0]["id"] == approval_id
    assert isinstance(delivered[0]["exported_at"], str)
    export_final(ws, job, output, digest, tmp_path / "delivery", workflow=workflow)
    assert http.get(f"/jobs/{job}/approvals").json() == delivered


def test_cli_exports_existing_final_through_same_use_case(tmp_path, monkeypatch):
    ws, job, _output, workflow = setup(tmp_path)
    monkeypatch.setenv("EMA_WORKSPACE", str(ws.root))
    monkeypatch.setattr(cli_review, "_workflow", lambda *_: workflow)
    monkeypatch.setattr(cli_review, "_terminal", lambda: True)
    monkeypatch.setattr(cli_review.typer, "confirm", lambda *_args, **_kwargs: True)
    dest = tmp_path / "delivery"
    result = CliRunner().invoke(_app, ["job", "export", job, "--final", "--dest", str(dest)])
    assert result.exit_code == 0, result.output
    response = json.loads(result.stdout.splitlines()[-1])
    assert response["folder"] == str(dest)
    assert len(response["files"]) == 3


def test_real_audit_readiness_allows_final_after_a_newer_draft(tmp_path, monkeypatch):
    ws, job, http, headers, output = approved.__wrapped__(tmp_path, monkeypatch)
    revision = http.get(f"/jobs/{job}").json()["revision"]
    started = http.post(
        f"/jobs/{job}/stages/audit_render", json={"on_revision": revision}, headers=headers
    )
    assert started.status_code == 202, started.text
    list(subscribe(ws, job))
    checks = http.get(f"/jobs/{job}/export/checks").json()
    assert checks["readiness"]["final_ok"], checks["readiness"]["blocking"]
    assert checks["final"]["output_id"] == output
    delivered = http.post(
        f"/jobs/{job}/export",
        json={
            "output_id": output,
            "readiness_hash": checks["readiness_hash"],
            "confirm": True,
            "dest_dir": str(tmp_path / "delivered"),
        },
        headers=headers,
    )
    assert delivered.status_code == 200, delivered.text
    assert {Path(file["name"]).suffix for file in delivered.json()["files"]} == {".docx", ".pdf"}
    assert http.get(f"/jobs/{job}/approvals").json()[0]["exported_at"]


def test_invalid_destination_is_a_4xx_before_approval(tmp_path, monkeypatch):
    ws, job, output, workflow = setup(tmp_path)
    monkeypatch.setattr(export_routes, "workflow_for", lambda *_: workflow)
    http, headers = _session(ws)
    checks = http.get(f"/jobs/{job}/export/checks").json()
    file = tmp_path / "file"
    file.write_text("existing", encoding="utf-8")
    body = {
        "output_id": output,
        "readiness_hash": checks["readiness_hash"],
        "confirm": True,
    }
    for destination, expected in [("\0", 422), (str(file), 400)]:
        response = http.post(
            f"/jobs/{job}/export", json={**body, "dest_dir": destination}, headers=headers
        )
        assert response.status_code == expected, response.text
    assert http.get(f"/jobs/{job}/approvals").json() == []
    assert file.read_text(encoding="utf-8") == "existing"
