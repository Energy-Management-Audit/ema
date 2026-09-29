"""Synthetic final export preserves field corrections and the HTTP contract."""

import time
from pathlib import Path
from types import SimpleNamespace

from tests.audit_structure import RETAINED_CONTENT, confirm_retained_content
from tests.unit.test_api_contract import evidence, session
from tests.workspace_jobs import create_job

from ema.api.mock import preview_pdf
from ema.audit.catalogue import CATALOGUE, AuditFact
from ema.core.jobs import StageOutcome, run_stage, status
from ema.core.review import propose
from ema.core.workspace import Workspace


def test_http_rerun_undo_and_synthetic_final_export(tmp_path: Path, monkeypatch) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    field = propose(
        ws, job, AuditFact.COMPANY_NAME.value, "Before", [evidence("before")], state="extracted"
    )
    client, headers = session(ws)
    correction = client.post(
        f"/jobs/{job}/fields/{field.id}/decide",
        json={"action": "correct", "value": "Corrected", "on_revision": field.revision},
        headers=headers,
    )
    assert correction.status_code == 200
    propose(ws, job, AuditFact.COMPANY_NAME.value, "Before", [evidence("rerun")], state="extracted")
    assert len(client.get(f"/jobs/{job}/conflicts").json()) == 1
    assert (
        client.post(f"/jobs/{job}/log/{correction.json()['id']}/undo", headers=headers).status_code
        == 409
    )
    assert (
        client.post(
            f"/jobs/{job}/export",
            json={
                "dest_dir": None,
                "output_id": "synthetic",
                "readiness_hash": "synthetic",
                "confirm": True,
            },
            headers=headers,
        ).status_code
        == 409
    )
    for section in CATALOGUE:
        if section.id in RETAINED_CONTENT:
            continue
        current_revision = next(
            state["revision"]
            for state in client.get(f"/jobs/{job}/sections").json()
            if state["section_id"] == section.id
        )
        reply = client.patch(
            f"/jobs/{job}/sections/{section.id}",
            json={"status": "n/a", "confirm": True, "on_revision": current_revision},
            headers=headers,
        )
        assert reply.status_code == 200
    assert client.get(f"/jobs/{job}/export/checks").json()["readiness"]["final_ok"] is False
    current = client.get(f"/jobs/{job}/fields").json()[0]
    choice = current["alternatives"][0]["id"]
    resolved = client.post(
        f"/jobs/{job}/fields/{field.id}/decide",
        json={"action": "choose", "alternative": choice, "on_revision": current["revision"]},
        headers=headers,
    )
    assert resolved.status_code == 200
    assert (
        client.post(f"/jobs/{job}/log/{resolved.json()['id']}/undo", headers=headers).status_code
        == 200
    )
    assert client.get(f"/jobs/{job}/export/checks").json()["readiness"]["final_ok"] is False
    current = client.get(f"/jobs/{job}/fields").json()[0]
    assert (
        client.post(
            f"/jobs/{job}/fields/{field.id}/decide",
            json={"action": "choose", "alternative": choice, "on_revision": current["revision"]},
            headers=headers,
        ).status_code
        == 200
    )
    confirm_retained_content(ws, job)
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert checks["readiness"]["final_ok"] is True, checks["readiness"]

    monkeypatch.setattr(
        "ema.audit.render_report.configured_base", lambda _: SimpleNamespace(inputs={})
    )

    def save(ctx):  # type: ignore[no-untyped-def]
        (ctx.artifact_dir() / "render-inputs.json").write_text("{}", encoding="utf-8")
        path = ctx.artifact_dir() / "synthetic.pdf"
        path.write_bytes(preview_pdf())
        ctx.save_output(path, "synthetic.pdf")
        document = ctx.artifact_dir() / "synthetic.docx"
        document.write_bytes(b"synthetic final")
        ctx.save_output(document, "synthetic.docx", kind="final")
        return StageOutcome()

    run_stage(ws, job, "audit_final", save)
    deadline = time.monotonic() + 5
    while status(ws, job).state == "running" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert status(ws, job).runs[-1]["state"] == "ready"
    with ws.connect() as db:
        output_id = str(
            db.execute("SELECT id FROM outputs WHERE job_id=? AND kind='final'", (job,)).fetchone()[
                0
            ]
        )
    assert client.get(f"/jobs/{job}/outputs/{output_id}").content == b"synthetic final"
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert (
        client.post(
            f"/jobs/{job}/export",
            json={
                "dest_dir": None,
                "output_id": output_id,
                "readiness_hash": checks["readiness_hash"],
            },
            headers=headers,
        ).status_code
        == 422
    )
    result = client.post(
        f"/jobs/{job}/export",
        json={
            "dest_dir": None,
            "output_id": output_id,
            "readiness_hash": checks["readiness_hash"],
            "confirm": True,
        },
        headers=headers,
    )
    assert result.status_code == 200, result.text
    assert set(result.json()) == {"approved_at", "files", "folder"}
    assert Path(result.json()["files"][0]["path"]).read_bytes() == preview_pdf()
