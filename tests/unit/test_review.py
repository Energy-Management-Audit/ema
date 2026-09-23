"""Synthetic review and approval integration."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from ema.cli import _app
from ema.cli import review as cli_review
from ema.core.errors import EmaError
from ema.core.jobs import StageOutcome, create_job, run_stage, status
from ema.core.review import (
    accept_batch,
    approve_final,
    base_readiness,
    decide,
    export,
    fields,
    log,
    mark_absent,
    propose,
    readiness_hash,
    undo,
)
from ema.core.review.models import Evidence, Field, FieldSpec, PdfText, Photo, Readiness
from ema.core.workspace import Workspace

CATALOGUE = [
    FieldSpec(key="source", label="Sursă", value_type="number"),
    FieldSpec(key="conflict", label="Conflict", value_type="number"),
    FieldSpec(key="missing", label="Lipsă", value_type="number", required=True),
]


def evidence(name: str, *, vision: bool = False) -> Evidence:
    return Evidence(
        id=name,
        file_sha="synthetic",
        locator=Photo() if vision else PdfText(page=1, span=name),
        method="questionnaire",
        retrieved_at=datetime.now(UTC),
        highlight="none",
    )


def get(ws: Workspace, job: str, key: str) -> Field:
    return next(item for item in fields(ws, job) if item.key == key)


def assert_error(code: str, fn: object) -> None:
    with pytest.raises(EmaError) as caught:
        fn()  # type: ignore[operator]
    assert caught.value.code == code


class FakeWorkflow:
    def readiness(self, ws: Workspace, job: str) -> Readiness:
        return base_readiness(ws, job, CATALOGUE)

    def readiness_snapshot(self, ws: Workspace, job: str) -> dict[str, object]:
        with ws.connect() as db:
            row = db.execute("SELECT settings_revision FROM jobs WHERE id=?", (job,)).fetchone()
        return {"settings_revision": int(row[0])}

    def render(self, ws: Workspace, job: str, kind: str) -> str:
        def stage(ctx):  # type: ignore[no-untyped-def]
            ctx.read_review_row("fields", get(ws, job, "source").id)
            source = ctx.artifact_dir() / "synthetic.txt"
            source.write_text(kind)
            ctx.save_output(source, f"{kind}.txt", kind=kind)
            return StageOutcome()

        run_stage(ws, job, "render", stage)
        for _ in range(200):
            if status(ws, job).state != "running":
                break
            time.sleep(0.01)
        assert status(ws, job).runs[-1]["publication"] == "current"
        with ws.connect() as db:
            return str(
                db.execute(
                    "SELECT id FROM outputs WHERE job_id=? ORDER BY rowid DESC", (job,)
                ).fetchone()[0]
            )


def setup(ws: Workspace) -> str:
    job = create_job(ws, "piee", "synthetic", 2026)
    propose(ws, job, CATALOGUE[0], 10, [evidence("first")], state="extracted")
    propose(ws, job, CATALOGUE[1], 20, [evidence("second")], state="extracted")
    propose(ws, job, CATALOGUE[1], 21, [evidence("third")], state="extracted")
    mark_absent(ws, job, CATALOGUE[2], "not_found")
    return job


def test_review_journal_undo_readiness_and_approval(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = setup(ws)
    workflow = FakeWorkflow()
    ready = workflow.readiness(ws, job)
    assert ready.draft_ok and not ready.final_ok
    assert {issue.code for issue in ready.blocking} == {"missing", "conflict"}

    source = get(ws, job, "source")
    first = decide(ws, job, source.id, "correct", source.revision, "user", value=11)
    rerun = propose(ws, job, CATALOGUE[0], 10, [evidence("rerun")], state="extracted")
    assert rerun.value == 11 and rerun.confidence == "conflict"
    second = decide(ws, job, source.id, "correct", rerun.revision, "user", value=12)
    with pytest.raises(EmaError) as caught:
        undo(ws, job, first.id, "user")
    assert caught.value.code == "decision_superseded" and caught.value.detail == second.id
    undo(ws, job, second.id, "user")
    assert get(ws, job, "source").value == 11
    # The re-run's candidate must survive; undoing d1 would erase it.
    with pytest.raises(EmaError) as changed:
        undo(ws, job, first.id, "user")
    assert changed.value.code == "field_changed"
    assert changed.value.detail == str(get(ws, job, "source").revision)
    assert_error("stale_revision", lambda: decide(ws, job, source.id, "accept", 1, "user"))

    source = get(ws, job, "source")
    chosen_source = next(item.id for item in source.alternatives if item.value == 11)
    decide(ws, job, source.id, "choose", source.revision, "user", alternative=chosen_source)

    conflict = get(ws, job, "conflict")
    assert len(conflict.alternatives) == 2
    decide(
        ws,
        job,
        conflict.id,
        "choose",
        conflict.revision,
        "user",
        alternative=conflict.alternatives[0].id,
    )
    missing = get(ws, job, "missing")
    decide(ws, job, missing.id, "correct", missing.revision, "user", value=30)
    assert workflow.readiness(ws, job).final_ok
    output = workflow.render(ws, job, "final")
    destination = tmp_path / "export.txt"
    assert_error(
        "approval_required",
        lambda: export(ws, job, workflow, final=True, dest=destination, actor="agent"),
    )
    digest = readiness_hash(ws, job, workflow.readiness(ws, job), workflow)
    approve_final(ws, job, output, digest, "user")
    assert export(ws, job, workflow, final=True, dest=destination, actor="agent") == destination
    assert destination.read_text() == "final"
    current = get(ws, job, "source")
    decide(ws, job, current.id, "accept", current.revision, "user")
    assert_error(
        "approval_required",
        lambda: export(ws, job, workflow, final=True, dest=destination, actor="user"),
    )
    approve_final(
        ws, job, output, readiness_hash(ws, job, workflow.readiness(ws, job), workflow), "user"
    )
    assert_error(
        "output_stale",
        lambda: export(ws, job, workflow, final=True, dest=destination, actor="user"),
    )
    assert_error("approval_requires_user", lambda: approve_final(ws, job, output, digest, "agent"))
    assert len(log(ws, job)) == 7


def test_cli_review_and_noninteractive_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = setup(ws)
    monkeypatch.setenv("EMA_WORKSPACE", str(ws.root))
    monkeypatch.setitem(cli_review.WORKFLOWS, "piee", FakeWorkflow())
    runner = CliRunner()
    result = runner.invoke(_app, ["job", "checks", job])
    assert result.exit_code == 0, result.output
    assert not json.loads(result.stdout)["final_ok"]
    source = get(ws, job, "source")
    result = runner.invoke(
        _app,
        ["job", "decide", job, source.id, "correct", "11", "--on-revision", str(source.revision)],
    )
    assert result.exit_code == 0, result.output
    assert get(ws, job, "source").value == 11
    result = runner.invoke(_app, ["job", "log", job])
    assert result.exit_code == 0 and len(json.loads(result.stdout)) == 1
    result = runner.invoke(_app, ["job", "undo", job, json.loads(result.stdout)[0]["id"]])
    assert result.exit_code == 0, result.output
    assert get(ws, job, "source").value == 10
    result = runner.invoke(
        _app, ["job", "export", job, "--final", "--dest", str(tmp_path / "final.txt")]
    )
    assert result.exit_code == 1
    assert not (tmp_path / "final.txt").exists()
    conflict = get(ws, job, "conflict")
    result = runner.invoke(
        _app,
        [
            "job",
            "decide",
            job,
            conflict.id,
            "choose",
            "--on-revision",
            str(conflict.revision),
            "--alternative",
            conflict.alternatives[0].id,
        ],
    )
    assert result.exit_code == 0, result.output
    missing = get(ws, job, "missing")
    result = runner.invoke(
        _app,
        ["job", "decide", job, missing.id, "correct", "30", "--on-revision", str(missing.revision)],
    )
    assert result.exit_code == 0, result.output
    monkeypatch.setattr(cli_review, "_terminal", lambda: True)
    command = ["job", "export", job, "--final", "--dest", str(tmp_path / "final.txt")]
    denied = runner.invoke(_app, command, input="n\n")
    assert denied.exit_code == 2 and not (tmp_path / "final.txt").exists()
    assert "rendered_path" in denied.stdout
    assert denied.stdout.index("rendered_path") < denied.stdout.index("Aprobați")
    assert denied.stdout.count("Aprobați") == 1
    accepted = runner.invoke(_app, command, input="y\n")
    assert accepted.exit_code == 0, accepted.output
    assert (tmp_path / "final.txt").read_text() == "final"


def test_final_export_rejects_draft_and_older_output(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = setup(ws)
    workflow = FakeWorkflow()
    conflict = get(ws, job, "conflict")
    decide(
        ws,
        job,
        conflict.id,
        "choose",
        conflict.revision,
        "user",
        alternative=conflict.alternatives[0].id,
    )
    missing = get(ws, job, "missing")
    decide(ws, job, missing.id, "correct", missing.revision, "user", value=30)
    draft = workflow.render(ws, job, "draft")
    digest = readiness_hash(ws, job, workflow.readiness(ws, job), workflow)
    destination = tmp_path / "final.txt"
    assert_error("output_not_final", lambda: approve_final(ws, job, draft, digest, "user"))
    assert_error(
        "output_not_final",
        lambda: export(ws, job, workflow, final=True, dest=destination, actor="user"),
    )
    final = workflow.render(ws, job, "final")
    approve_final(ws, job, final, digest, "user")
    newer_draft = workflow.render(ws, job, "draft")
    assert newer_draft != final
    assert_error("output_stale", lambda: approve_final(ws, job, final, digest, "user"))
    assert_error(
        "output_not_final",
        lambda: export(ws, job, workflow, final=True, dest=destination, actor="user"),
    )
    assert not destination.exists()


def test_final_export_rechecks_workflow_snapshot(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)

    class Workflow(FakeWorkflow):
        def readiness(self, ws: Workspace, job: str) -> Readiness:
            return Readiness(draft_ok=True, final_ok=True)

    workflow = Workflow()
    # The fake renderer expects a source field.
    propose(ws, job, "source", 10, [evidence("source")], state="extracted")
    output = workflow.render(ws, job, "final")
    digest = readiness_hash(ws, job, workflow.readiness(ws, job), workflow)
    approve_final(ws, job, output, digest, "user")
    with ws.connect() as db:
        db.execute("UPDATE jobs SET settings_revision=settings_revision+1 WHERE id=?", (job,))
    assert_error(
        "approval_required",
        lambda: export(ws, job, workflow, final=True, dest=tmp_path / "final.txt", actor="user"),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"value": None, "presence": "found"},
        {"value": 1, "presence": "not_found"},
        {"state": "manual", "evidence": []},
        {"presence": "failed", "value": None, "failure": None},
        {"confidence": "conflict"},
        {"chosen": "missing"},
    ],
)
def test_invalid_field_states(changes: dict[str, object]) -> None:
    initial = dict(
        id="f",
        job_id="j",
        key="k",
        label="K",
        value_type="number",
        value=1,
        state="extracted",
        presence="found",
        confidence="exact",
    )
    with pytest.raises(ValidationError):
        Field.model_validate({**initial, **changes})


def test_batch_is_atomic_and_manual_evidence_immutable(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    first = propose(ws, job, "a", 1, [evidence("a")], state="extracted")
    second = propose(ws, job, "b", 2, [evidence("b", vision=True)], state="extracted")
    assert_error(
        "stale_revision", lambda: accept_batch(ws, job, [(first.id, 1), (second.id, 0)], "user")
    )
    assert log(ws, job) == []
    result = accept_batch(ws, job, [(first.id, 1), (second.id, 1)], "user")
    assert len(result) == 2 and result[0].batch_id == result[1].batch_id
    assert_error(
        "evidence_immutable",
        lambda: propose(ws, job, "c", 3, [evidence("a", vision=True)], state="extracted"),
    )


def test_numeric_value_keeps_source_precision(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    value = Decimal("123456789.1234567890123456789")
    proposed = propose(ws, job, "precise", value, [evidence("precise")], state="extracted")
    assert proposed.value == value
    assert get(ws, job, "precise").value == value
    corrected = decide(
        ws,
        job,
        proposed.id,
        "correct",
        proposed.revision,
        "user",
        value=Decimal("123456789.1234567890123456790"),
    )
    assert log(ws, job)[0].after.value == corrected.after.value


def test_review_change_stales_running_stage(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    field = propose(ws, job, "a", 1, [evidence("a")], state="extracted")
    read, release = threading.Event(), threading.Event()

    def stage(ctx):  # type: ignore[no-untyped-def]
        ctx.read_review_row("fields", field.id)
        read.set()
        assert release.wait(2)
        return StageOutcome()

    run_stage(ws, job, "draft", stage)
    assert read.wait(2)
    decide(ws, job, field.id, "accept", field.revision, "user")
    release.set()
    for _ in range(200):
        if status(ws, job).runs[-1]["publication"]:
            break
        time.sleep(0.01)
    assert status(ws, job).runs[-1]["publication"] == "stale"


def test_evidence_keeps_file_referenced_until_job_delete(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    source = tmp_path / "source.txt"
    source.write_text("synthetic evidence")
    sha = ws.add_file("synthetic", source)
    proof = evidence("backed")
    proof = proof.model_copy(update={"file_sha": sha})
    propose(ws, job, "a", 1, [proof], state="extracted")
    with ws.connect() as db:
        relative = db.execute("SELECT relative_path FROM files WHERE sha=?", (sha,)).fetchone()[0]
        db.execute("UPDATE files SET added_at=0 WHERE sha=?", (sha,))
        assert relative in {item[0] for item in ws.referenced_files(db)}
    ws.gc()
    assert ws.path(relative).exists()
    ws.delete_job(job)
    with ws.connect() as db:
        assert db.execute("SELECT 1 FROM fields WHERE job_id=?", (job,)).fetchone() is None
    ws.gc()
    assert not ws.path(relative).exists()
