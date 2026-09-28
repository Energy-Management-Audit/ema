"""A changed configured base makes confirmed render-drafted sections stale everywhere (D6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.audit.render_seams import outputs
from tests.unit.audit.section_marks_seams import (
    base_sha,
    by_id,
    draft,
    journal,
    marked_job,
    session,
)

from ema.audit import base_entry, workflow
from ema.audit.catalogue import CATALOGUE
from ema.audit.sections import Status, refresh_staleness, set_status
from ema.audit.sections_bulk import patch_sections
from ema.audit.workflow import AuditWorkflow
from ema.core.config import Settings
from ema.core.errors import EmaError
from ema.core.jobs import subscribe
from ema.core.workspace import Workspace

ORDER = [section.id for section in CATALOGUE]


def _ready_for_final(ws: Workspace, job: str) -> list[str]:
    """Every render-drafted section confirmed by the user, the rest n/a: the final is ready."""
    set_status(ws, job, "ch4.bilant_real", Status.NA, "user", "golden")  # its writer is not seamed
    draft(ws, job)
    drafted = [s for s in by_id(ws, job).values() if s.status == Status.DRAFTED and not s.stale]
    patch_sections(
        ws,
        job,
        [
            {
                "section_id": s.section_id,
                "status": "done",
                "on_revision": s.revision,
                "confirm": True,
            }
            for s in drafted
        ],
    )
    for state in by_id(ws, job).values():
        if state.status != Status.DONE:
            set_status(ws, job, state.section_id, Status.NA, "user", "golden")
    readiness = AuditWorkflow().readiness(ws, job)
    assert readiness.final_ok, [issue.message for issue in readiness.blocking]
    return [state.section_id for state in drafted]


def _switch(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setenv("EMA_AUDIT_BASE_DOCUMENT", str(path))


def test_t5_a_changed_base_turns_done_into_a_stale_draft_with_an_ema_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = marked_job(tmp_path, monkeypatch)
    confirmed = _ready_for_final(ws, job)
    old = f"base:{base_sha(tmp_path)}"
    refresh_staleness(ws, job, base_sha="f" * 64)
    states = by_id(ws, job)
    for section_id in confirmed:
        assert (states[section_id].status, states[section_id].stale) == (Status.DRAFTED, True)
        assert states[section_id].changed_input == old
        assert journal(ws, job, section_id)[-1] == ("ema", old)


def test_t7_switching_the_base_refuses_every_final_path_and_the_marks_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = marked_job(tmp_path, monkeypatch)
    confirmed = _ready_for_final(ws, job)
    client, headers = session(ws)
    revision = client.get(f"/jobs/{job}").json()["revision"]
    started = client.post(
        f"/jobs/{job}/stages/audit_final", json={"on_revision": revision}, headers=headers
    )
    assert started.status_code == 202, started.json()
    list(subscribe(ws, job))
    report = client.get(f"/jobs/{job}/audit/report").json()
    assert report["final"]["state"] == "ready", _error(ws, job)
    final_id = report["final"]["docx_output_id"]
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert checks["readiness"]["final_ok"]
    x = tmp_path / "base.docx"
    y = tmp_path / "base-renewed.docx"
    y.write_bytes(x.read_bytes() + b" renewed")
    _switch(monkeypatch, y)
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
    assert exported.status_code == 409
    assert exported.json()["type"] == "urn:ema:error:not_ready"
    old = f"base:{base_sha(tmp_path)}"
    with ws.connect() as db:  # read raw: no readiness call may have made these marks
        rows = {
            str(row["section_id"]): json.loads(row["data"])
            for row in db.execute(
                "SELECT section_id,data FROM section_states WHERE job_id=?", (job,)
            )
        }
    for section_id in confirmed:
        assert (rows[section_id]["status"], rows[section_id]["stale"]) == ("drafted", True)
        assert rows[section_id]["changed_input"] == old
        assert journal(ws, job, section_id)[-1] == ("ema", old)
    blocking = AuditWorkflow().readiness(ws, job).blocking
    stale = [issue.message for issue in blocking if issue.code == "stale"]
    assert len(stale) == len(confirmed)
    with pytest.raises(EmaError) as refused:
        AuditWorkflow().start_final(ws, job)
    assert refused.value.code == "not_ready"
    assert not client.get(f"/jobs/{job}/export/checks").json()["readiness"]["final_ok"]
    _switch(monkeypatch, x)  # the old base again: a draft and a human are still needed
    assert all(by_id(ws, job)[section_id].stale for section_id in confirmed)
    assert not AuditWorkflow().readiness(ws, job).final_ok


def test_t8_a_base_switched_after_readiness_fails_the_final_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = marked_job(tmp_path, monkeypatch)
    confirmed = _ready_for_final(ws, job)
    y = tmp_path / "base-renewed.docx"
    y.write_bytes((tmp_path / "base.docx").read_bytes() + b" renewed")
    original = workflow.start_audit_render

    def switched(*args: object, **kwargs: object) -> str:
        _switch(monkeypatch, y)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(workflow, "start_audit_render", switched)
    run = AuditWorkflow().start_final(ws, job)
    list(subscribe(ws, job))
    with ws.connect() as db:
        record = db.execute("SELECT state,error FROM runs WHERE id=?", (run,)).fetchone()
        event = db.execute(
            "SELECT payload FROM job_events WHERE run_id=? AND type='stage_failed'", (run,)
        ).fetchone()
    assert record["state"] == "failed"
    assert json.loads(event["payload"]) == {
        "code": "base_changed",
        "message": "Baza raportului s-a schimbat. Refaceţi ciorna.",
    }
    assert record["error"] == ",".join(sorted(confirmed, key=ORDER.index))
    assert [name for name, kind in outputs(ws, job) if kind == "final"] == []
    assert all(by_id(ws, job)[section_id].stale for section_id in confirmed)


def test_t9_no_readable_base_leaves_base_entries_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert base_entry.base_sha(Settings()) is None
    assert base_entry.base_sha(Settings(audit_base_document=tmp_path / "missing.docx")) is None
    present = tmp_path / "present.docx"
    present.write_bytes(b"one")
    first = base_entry.base_sha(Settings(audit_base_document=present))
    present.write_bytes(b"other bytes")
    assert base_entry.base_sha(Settings(audit_base_document=present)) not in {None, first}
    ws, job = marked_job(tmp_path, monkeypatch)
    confirmed = _ready_for_final(ws, job)
    before = by_id(ws, job)
    monkeypatch.delenv("EMA_AUDIT_BASE_DOCUMENT")
    refresh_staleness(ws, job)
    _switch(monkeypatch, tmp_path / "missing.docx")
    refresh_staleness(ws, job)
    assert by_id(ws, job) == before
    assert all(before[section_id].status == Status.DONE for section_id in confirmed)


def _error(ws: Workspace, job: str) -> str:
    with ws.connect() as db:
        return str(
            db.execute(
                "SELECT error FROM runs WHERE job_id=? ORDER BY ended_at DESC", (job,)
            ).fetchone()[0]
        )
