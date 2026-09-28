"""A synthetic job whose draft render marks sections, and readers of its journal (D6/D7)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.unit.audit.render_seams import (
    FakeWord,
    fill_writer,
    narrative_writer,
    run_render,
    synthetic_render,
    write_intros,
    write_narrative,
)

from ema.api import create_app
from ema.audit import render
from ema.audit.sections import recompute_ready, statuses
from ema.core.review.section_transition import SectionState
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def marked_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Workspace, str]:
    """Her intros written, every section computed, the chapter writers write text, Word present."""
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    write_intros(ws, job)
    write_narrative(ws, job, "ch4.concluzii", "Consumul a scăzut.")
    recompute_ready(ws, job)
    monkeypatch.setattr(render, "write_draft", fill_writer("ch2.date_generale", "ch3.flux"))
    monkeypatch.setattr(render, "write_four", narrative_writer("ch4.concluzii"))
    monkeypatch.setattr(render, "word_available", lambda settings: True)
    monkeypatch.setattr(render, "word_automation", lambda settings: FakeWord())
    return ws, job


def base_sha(tmp_path: Path) -> str:
    return hashlib.sha256((tmp_path / "base.docx").read_bytes()).hexdigest()


def by_id(ws: Workspace, job: str) -> dict[str, SectionState]:
    return {state.section_id: state for state in statuses(ws, job)}


def journal(ws: Workspace, job: str, section_id: str) -> list[tuple[str, str | None]]:
    """(actor, detail) of each section decision, oldest first."""
    with ws.connect() as db:
        rows = db.execute(
            "SELECT data FROM decisions WHERE job_id=? AND field_id=? ORDER BY seq",
            (job, section_id),
        ).fetchall()
    entries = [json.loads(row["data"]) for row in rows]
    return [(item["actor"], item["detail"]) for item in entries if item["target_kind"] == "section"]


def publication(ws: Workspace, run: str) -> str:
    with ws.connect() as db:
        return str(db.execute("SELECT publication FROM runs WHERE id=?", (run,)).fetchone()[0])


def draft(ws: Workspace, job: str) -> dict[str, object]:
    record = run_render(ws, job)
    assert record["state"] == "ready", record["error"]
    return record


def session(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(ws, 8766, launch_code="code"), base_url=BASE)
    headers = {"X-Ema-CSRF": client.post("/session", json={"code": "code"}).json()["csrf"]}
    return client, headers
