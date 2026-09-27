"""A final never carries AI wording: the rendered document's whole text is read before it ships."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document
from tests.unit.audit.render_seams import (
    TITLES,
    FakeWord,
    fill_writer,
    narrative_writer,
    outputs,
    run_render,
    synthetic_render,
    write_narrative,
)

from ema.audit import render
from ema.audit.render_steps import ai_wording_hits
from ema.audit.sections import Status, set_status
from ema.audit.workflow import AuditWorkflow
from ema.core.workspace import Workspace


def test_every_text_part_is_read(tmp_path: Path) -> None:
    docx = tmp_path / "gate.docx"
    document = Document()
    document.sections[0].header.paragraphs[0].text = "Redactat cu GPT"
    document.add_paragraph(TITLES["ch1"], style="Heading 1")
    document.add_paragraph("Angajaţi ai unor persoane juridice.")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Tabel scris de IA"
    document.save(str(docx))
    assert ai_wording_hits(docx, []) == ["ch1", "header1"]
    clean = tmp_path / "clean.docx"
    Document().save(str(clean))
    assert ai_wording_hits(clean, []) == []


@pytest.fixture
def final(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Workspace, str]:
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    set_status(ws, job, "ch4.bilant_real", Status.NA, "user")
    monkeypatch.setattr(render, "write_draft", fill_writer("ch2.date_generale", "ch3.flux"))
    monkeypatch.setattr(render, "write_four", narrative_writer("ch4.concluzii"))
    monkeypatch.setattr(render, "word_available", lambda settings: True)
    monkeypatch.setattr(render, "word_automation", lambda settings: FakeWord())
    return ws, job


def _failure(ws: Workspace, job: str) -> dict[str, object]:
    with ws.connect() as db:
        row = db.execute(
            "SELECT payload FROM job_events WHERE job_id=? AND type='stage_failed' "
            "ORDER BY seq DESC LIMIT 1",
            (job,),
        ).fetchone()
    return json.loads(row["payload"])


def test_ai_wording_in_a_ch4_text_refuses_the_final_naming_the_field(
    final: tuple[Workspace, str],
) -> None:
    ws, job = final
    write_narrative(ws, job, "ch4.concluzii", "Acest raport a fost generat de AI")
    readiness = AuditWorkflow().readiness(ws, job)
    assert [issue.message for issue in readiness.blocking if issue.code == "ai_wording"] == [
        f"Textul menţionează AI („AI”): {TITLES['ch4.concluzii']}"
    ]
    record = run_render(ws, job, "final")
    assert record["state"] == "failed"
    assert _failure(ws, job) == {
        "code": "audit_ai_wording",
        "message": "Raportul final conţine formulări despre AI.",
    }
    assert str(record["error"]).split("; ") == ["narrative.ch4.concluzii", "ch4.concluzii"]
    assert outputs(ws, job) == []


def test_clean_text_passes(final: tuple[Workspace, str]) -> None:
    ws, job = final
    write_narrative(ws, job, "ch4.concluzii", "Consumul a scăzut după modernizare.")
    record = run_render(ws, job, "final")
    assert record["state"] == "ready", record["error"]
    assert [name for name, _ in outputs(ws, job)] == ["Audit-final.pdf", "Audit-final.docx"]
