"""The PIEE final render opens the document in Word once."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.workspace_jobs import create_job

from ema.core.jobs import StageContext, StageOutcome, run_stage, subscribe
from ema.core.review.models import Readiness
from ema.core.workspace import Workspace
from ema.piee import review_workflow
from ema.piee.review_workflow import PieeWorkflow


class RecordingWord:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def toc_and_pdf(self, docx: Path, pdf: Path) -> None:
        self.calls.append(("toc_and_pdf", docx.name, pdf.name))
        docx.write_bytes(b"page numbers set")
        pdf.write_bytes(b"%PDF-1.7 synthetic")


def test_final_render_makes_one_word_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2025)

    def draft(ctx: StageContext) -> StageOutcome:
        docx = ctx.artifact_dir() / "PIEE-draft.docx"
        docx.write_bytes(b"synthetic draft")
        workbook = ctx.artifact_dir() / "Prelucrare-date.xlsx"
        workbook.write_bytes(b"synthetic workbook")
        ctx.save_output(workbook, "Prelucrare-date.xlsx")
        ctx.save_output(docx, "PIEE-draft.docx")
        return StageOutcome()

    run_stage(ws, job, "piee_generate", draft)
    for _ in subscribe(ws, job):
        pass
    base = tmp_path / "base"
    base.mkdir()
    (base / "base-identity.json").write_text(json.dumps([]), encoding="utf-8")
    word = RecordingWord()
    ready = Readiness(draft_ok=True, final_ok=True)
    monkeypatch.setattr(PieeWorkflow, "readiness", lambda self, ws, job: ready)
    monkeypatch.setattr(review_workflow, "word_available", lambda settings: True)
    monkeypatch.setattr(review_workflow, "word_automation", lambda settings: word)
    monkeypatch.setattr(review_workflow, "base_directory", lambda ws: base)
    monkeypatch.setattr(
        review_workflow, "load_approved_base", lambda base: SimpleNamespace(base_sha="synthetic")
    )
    monkeypatch.setattr(review_workflow, "check_standalone", lambda docx: [])
    monkeypatch.setattr(review_workflow, "leftover_issues", lambda docx, denylist: [])
    output = PieeWorkflow().render(ws, job, "final")
    assert word.calls == [("toc_and_pdf", "PIEE-final.docx", "PIEE-final.pdf")]
    with ws.connect() as db:
        rows = db.execute(
            "SELECT id,relative_path,kind FROM outputs WHERE job_id=? ORDER BY seq", (job,)
        ).fetchall()
    final = next(row for row in rows if row["kind"] == "final")
    assert final["id"] == output
    assert ws.path(str(final["relative_path"])).read_bytes() == b"page numbers set"
    assert any(str(row["relative_path"]).endswith("PIEE-final.pdf") for row in rows)
