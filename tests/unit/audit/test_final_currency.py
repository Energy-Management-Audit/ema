"""An approved final is exactly what was rendered: any later input change makes it stale (B1)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.audit_structure import RETAINED_CONTENT, confirm_retained_content
from tests.unit.audit.render_seams import (
    FakeWord,
    fill_writer,
    narrative_writer,
    synthetic_render,
    write_narrative,
)

from ema.api import create_app
from ema.audit import render
from ema.audit.catalogue import CATALOGUE
from ema.audit.sections import Status, set_status
from ema.core.jobs import subscribe
from ema.core.review import decide, fields, propose
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"
KEPT = "ch4.concluzii"


def _done(ws: Workspace, job: str, section: str) -> None:
    set_status(ws, job, section, Status.READY, "ema")
    set_status(ws, job, section, Status.DRAFTED, "ema")
    set_status(ws, job, section, Status.DONE, "user")


@pytest.fixture
def approved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Workspace, str, TestClient, dict[str, str], str]:
    """A final rendered while ch4.concluzii is done and written; every other section n/a."""
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    confirm_retained_content(ws, job)
    for section in CATALOGUE:
        if section.id not in {KEPT, *RETAINED_CONTENT}:
            set_status(ws, job, section.id, Status.NA, "user")
    _done(ws, job, KEPT)
    write_narrative(ws, job, KEPT, "Consumul a scăzut după modernizare.")
    monkeypatch.setattr(render, "write_draft", fill_writer("ch2.date_generale", "ch3.flux"))
    monkeypatch.setattr(render, "write_four", narrative_writer(KEPT))
    monkeypatch.setattr(render, "word_available", lambda settings: True)
    monkeypatch.setattr(render, "word_automation", lambda settings: FakeWord())
    client = TestClient(create_app(ws, 8766, launch_code="code"), base_url=BASE)
    headers = {"X-Ema-CSRF": client.post("/session", json={"code": "code"}).json()["csrf"]}
    revision = client.get(f"/jobs/{job}").json()["revision"]
    started = client.post(
        f"/jobs/{job}/stages/audit_final", json={"on_revision": revision}, headers=headers
    )
    assert started.status_code == 202, started.json()
    list(subscribe(ws, job))
    report = client.get(f"/jobs/{job}/audit/report").json()
    assert report["final"]["state"] == "ready" and report["final"]["current"]
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert checks["readiness"]["final_ok"], checks["readiness"]["blocking"]
    return ws, job, client, headers, report["final"]["docx_output_id"]


def _refused_after_change(client: TestClient, headers: dict[str, str], job: str, output: str):
    checks = client.get(f"/jobs/{job}/export/checks").json()
    assert not checks["readiness"]["final_ok"]
    assert "final_stale" in [issue["code"] for issue in checks["readiness"]["blocking"]]
    assert client.get(f"/jobs/{job}/audit/report").json()["final"]["current"] is False
    exported = client.post(
        f"/jobs/{job}/export",
        json={
            "dest_dir": None,
            "output_id": output,
            "readiness_hash": checks["readiness_hash"],
            "confirm": True,
        },
        headers=headers,
    )
    assert exported.status_code == 409
    assert exported.json()["type"] == "urn:ema:error:not_ready"
    return checks


def test_done_then_na_after_the_final_refuses_the_old_final(
    approved: tuple[Workspace, str, TestClient, dict[str, str], str],
) -> None:
    ws, job, client, headers, output = approved
    set_status(ws, job, KEPT, Status.NA, "user")
    _refused_after_change(client, headers, job, output)
    # The stale final never blocks making the new one.
    revision = client.get(f"/jobs/{job}").json()["revision"]
    again = client.post(
        f"/jobs/{job}/stages/audit_final", json={"on_revision": revision}, headers=headers
    )
    assert again.status_code == 202, again.json()
    list(subscribe(ws, job))


def test_a_text_edited_after_the_final_refuses_the_old_final(
    approved: tuple[Workspace, str, TestClient, dict[str, str], str],
) -> None:
    ws, job, client, headers, output = approved
    field = next(item for item in fields(ws, job) if item.key == f"narrative.{KEPT}")
    decide(ws, job, field.id, "correct", field.revision, "user", value="Consumul a crescut.")
    _refused_after_change(client, headers, job, output)


def test_another_base_identity_refuses_the_old_final(
    approved: tuple[Workspace, str, TestClient, dict[str, str], str], tmp_path: Path
) -> None:
    _, job, client, headers, output = approved
    (tmp_path / "identity.json").write_text('["Alt Client de Bază SRL"]', encoding="utf-8")
    _refused_after_change(client, headers, job, output)


def test_a_new_field_the_render_looks_up_refuses_the_old_final(
    approved: tuple[Workspace, str, TestClient, dict[str, str], str],
) -> None:
    ws, job, client, headers, output = approved
    assert "audit.company_name" not in {field.key for field in fields(ws, job)}
    propose(ws, job, "audit.company_name", "Atelier Exemplu SRL", [], state="supplied")
    _refused_after_change(client, headers, job, output)


def test_a_deleted_field_refuses_the_old_final(
    approved: tuple[Workspace, str, TestClient, dict[str, str], str],
) -> None:
    ws, job, client, headers, output = approved
    with ws.connect() as db:
        db.execute("DELETE FROM fields WHERE job_id=? AND key=?", (job, f"narrative.{KEPT}"))
    _refused_after_change(client, headers, job, output)


def test_an_unrelated_new_field_keeps_the_final_current(
    approved: tuple[Workspace, str, TestClient, dict[str, str], str],
) -> None:
    ws, job, client, _, _ = approved
    propose(ws, job, "thermal.t1.max_temp", Decimal(71), [], state="extracted")
    assert client.get(f"/jobs/{job}/audit/report").json()["final"]["current"]
    assert client.get(f"/jobs/{job}/export/checks").json()["readiness"]["final_ok"]
