"""Both reference inputs exercise the PIEE review gate through generated jobs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ema.cli import _app
from ema.core.errors import EmaError
from ema.core.jobs import status, subscribe
from ema.core.review import decide, fields
from ema.core.workspace import Workspace
from ema.piee.review_workflow import PieeWorkflow
from ema.piee.workflow import GenerateRequest, start_generate

pytestmark = pytest.mark.golden


@pytest.mark.parametrize("case_name", ["piee-case-a", "piee-case-b"])
def test_review_decision_and_final_gate(
    reference_library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case_name: str
) -> None:
    base = next((reference_library / "piee/finished-programs").glob("*MODEL_2026.docx"))
    monkeypatch.setenv("EMA_PIEE_BASE_DOCUMENT", str(base))
    monkeypatch.setenv("EMA_PIEE_BASE_DIRECTORY", str(Path.home() / "Ema-dev/s8/base"))
    case = reference_library / "piee/cases" / case_name
    anexa = next(case.rglob("Anexa*.xlsx"))
    necesar = next(case.rglob("Necesar*.xls"), None)
    prelucrare = next(case.rglob("*Prelucrare*.xls*"))
    previous_piee = next((case / "final").glob("*.docx")) if case_name == "piee-case-b" else None
    ws = Workspace(tmp_path / "workspace")
    job, run = start_generate(
        ws, GenerateRequest("synthetic-client", 2025, anexa, necesar, prelucrare, previous_piee)
    )
    for _ in subscribe(ws, job):
        pass
    assert next(item for item in status(ws, job).runs if item["id"] == run)["state"] == "ready"
    if previous_piee is not None:
        with ws.connect() as db:
            assert (
                db.execute(
                    "SELECT 1 FROM slots WHERE job_id=? AND name='previous_piee'", (job,)
                ).fetchone()
                is not None
            )

    workflow = PieeWorkflow()
    conflict = next(field for field in fields(ws, job) if field.confidence == "conflict")
    assert any(issue.field_id == conflict.id for issue in workflow.readiness(ws, job).blocking)
    with pytest.raises(EmaError) as refused:
        workflow.render(ws, job, "final")
    assert refused.value.code == "not_ready"
    choice = next(item for item in conflict.alternatives if item.value == conflict.value)
    decide(ws, job, conflict.id, "choose", conflict.revision, "user", alternative=choice.id)
    assert not any(issue.field_id == conflict.id for issue in workflow.readiness(ws, job).blocking)
    for item in fields(ws, job, status="conflict"):
        selected = next(
            candidate for candidate in item.alternatives if candidate.value == item.value
        )
        decide(ws, job, item.id, "choose", item.revision, "user", alternative=selected.id)
    assert workflow.readiness(ws, job).final_ok

    class StubWord:
        def update_toc_pages(self, _docx: Path) -> None:
            pass

        def render_pdf(self, _docx: Path, pdf: Path) -> None:
            pdf.write_bytes(b"%PDF-1.4\n")

        def open_check(self, _docx: Path) -> None:
            pass

    monkeypatch.setattr("ema.piee.review_workflow.WordMac", StubWord)
    final_id = workflow.render(ws, job, "final")
    with ws.connect() as db:
        outputs = db.execute(
            "SELECT kind,relative_path FROM outputs WHERE job_id=? ORDER BY seq DESC LIMIT 3",
            (job,),
        ).fetchall()
    assert len(outputs) == 3
    assert [row["kind"] for row in outputs] == ["final", "draft", "draft"]
    assert final_id
    reviewed = next(item for item in fields(ws, job) if item.id == conflict.id)
    alternative = next(item for item in reviewed.alternatives if item.value != reviewed.value)
    decide(ws, job, reviewed.id, "choose", reviewed.revision, "user", alternative=alternative.id)
    assert any(issue.code == "review_override" for issue in workflow.readiness(ws, job).blocking)


def test_cli_generate_review_and_refuse_unresolved_final(
    reference_library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = next((reference_library / "piee/finished-programs").glob("*MODEL_2026.docx"))
    monkeypatch.setenv("EMA_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("EMA_PIEE_BASE_DOCUMENT", str(base))
    monkeypatch.setenv("EMA_PIEE_BASE_DIRECTORY", str(Path.home() / "Ema-dev/s8/base"))
    case = reference_library / "piee/cases/piee-case-b"
    anexa = next(case.rglob("Anexa*.xlsx"))
    prelucrare = next(case.rglob("*Prelucrare*.xls*"))
    runner = CliRunner()
    generated = runner.invoke(
        _app,
        [
            "piee",
            "generate",
            "--client",
            "synthetic-client",
            "--year",
            "2025",
            "--anexa",
            str(anexa),
            "--prelucrare",
            str(prelucrare),
        ],
    )
    assert generated.exit_code == 0
    job = json.loads(generated.output)["job"]
    checked = runner.invoke(_app, ["job", "checks", job])
    assert checked.exit_code == 0
    assert any(item["code"] == "conflict" for item in json.loads(checked.output)["blocking"])
    refused = runner.invoke(
        _app, ["job", "export", job, "--dest", str(tmp_path / "final.docx"), "--final"]
    )
    assert isinstance(refused.exception, EmaError)
    assert refused.exception.code == "not_ready"
    ws = Workspace(tmp_path / "workspace")
    conflicting = fields(ws, job, status="conflict")
    first = conflicting[0]
    selected = next(candidate for candidate in first.alternatives if candidate.value == first.value)
    decided = runner.invoke(
        _app,
        [
            "job",
            "decide",
            job,
            first.id,
            "choose",
            "--on-revision",
            str(first.revision),
            "--alternative",
            selected.id,
        ],
    )
    assert decided.exit_code == 0
    assert len(fields(ws, job, status="conflict")) == len(conflicting) - 1
