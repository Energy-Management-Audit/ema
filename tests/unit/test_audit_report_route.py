"""GET /jobs/{id}/audit/report: the newest draft and final render and whether Word is there."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.unit.audit.render_seams import FakeWord, synthetic_render
from tests.workspace_jobs import create_job

from ema.api import create_app
from ema.audit import render
from ema.core.jobs import subscribe
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def _client(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(ws, 8766, launch_code="code"), base_url=BASE)
    token = client.post("/session", json={"code": "code"}).json()["csrf"]
    return client, {"X-Ema-CSRF": token}


def test_report_lists_the_newest_draft_with_its_summary_and_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    client, headers = _client(ws)
    assert client.get(f"/jobs/{job}/audit/report").json() == {
        "draft": None,
        "final": None,
        "word": False,
    }
    monkeypatch.setattr(render, "word_available", lambda settings: True)
    monkeypatch.setattr(render, "word_automation", lambda settings: FakeWord())
    revision = client.get(f"/jobs/{job}").json()["revision"]
    started = client.post(
        f"/jobs/{job}/stages/audit_render", json={"on_revision": revision}, headers=headers
    )
    assert started.status_code == 202
    list(subscribe(ws, job))
    body = client.get(f"/jobs/{job}/audit/report").json()
    draft = body["draft"]
    assert (draft["run_id"], draft["state"], draft["current"]) == (
        started.json()["run_id"],
        "ready",
        True,
    )
    assert draft["ended_at"] and body["final"] is None
    names = {item["id"]: item["name"] for item in client.get(f"/jobs/{job}/outputs").json()}
    assert names[draft["docx_output_id"]] == "Audit-ciorna.docx"
    assert names[draft["pdf_output_id"]] == "Audit-ciorna.pdf"
    summary = draft["summary"]
    assert summary["kind"] == "draft" and summary["pdf"] and summary["toc_pages_set"]
    assert set(summary) == {
        "kind",
        "chapters",
        "tables",
        "charts",
        "markers",
        "fields_total",
        "fields_confirmed",
        "fields_manual",
        "unit_plan",
        "pdf",
        "toc_pages_set",
        "dropped",
        "failures",
        "charts_skipped",
    }
    assert summary["charts_skipped"] == []
    assert set(summary["chapters"][0]) == {"number", "title", "section_id", "page"}
    assert summary["unit_plan"]["processes_source"] == "default"


def test_report_errors(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    piee = create_job(ws, "piee", "synthetic", 2026)
    client, _ = _client(ws)
    wrong = client.get(f"/jobs/{piee}/audit/report")
    assert (wrong.status_code, wrong.json()["type"]) == (400, "urn:ema:error:wrong_job_type")
    missing = client.get("/jobs/nope/audit/report")
    assert (missing.status_code, missing.json()["type"]) == (404, "urn:ema:error:job_missing")
