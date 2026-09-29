"""PIEE final export refuses jobs without a reviewed draft."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.core.errors import EmaError
from ema.core.jobs import StageOutcome, run_stage, subscribe
from ema.core.review import propose
from ema.core.review.models import Cell, Evidence, FieldSpec
from ema.core.workspace import Workspace
from ema.piee.review_workflow import PieeWorkflow


def test_missing_draft_blocks_final_export_with_explicit_issues(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path / "workspace")
    job = create_job(workspace, "piee", "synthetic", 2025)
    workflow = PieeWorkflow()
    readiness = workflow.readiness(workspace, job)
    assert not readiness.final_ok
    assert {issue.code for issue in readiness.blocking} >= {"draft_missing"}
    with pytest.raises(EmaError) as missing:
        workflow.render(workspace, job, "draft")
    assert missing.value.code == "piee_output_missing"


def test_readiness_checks_untouched_and_package_errors_in_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    job = create_job(workspace, "piee", "synthetic", 2025)
    for key, value, kind in (
        ("identity.name", "Synthetic", "text"),
        ("annual.total_tep", Decimal("2"), "number"),
    ):
        propose(
            workspace,
            job,
            FieldSpec(key=key, label=key, value_type=kind, required=True),
            value,
            [
                Evidence(
                    id=key,
                    provenance="document",
                    file_sha="synthetic",
                    locator=Cell(sheet="Anexa", ref="A1"),
                    method="anexa",
                    retrieved_at=datetime.now(UTC),
                    highlight="exact",
                )
            ],
            state="extracted",
        )
    base = tmp_path / "base"
    base.mkdir()
    (base / "toc-manifest.json").write_text(json.dumps({"number_slots": ["toc"]}), encoding="utf-8")
    (base / "base-map.json").write_text("synthetic map", encoding="utf-8")
    monkeypatch.setattr("ema.piee.review_workflow.base_directory", lambda ws: base)

    def stage(ctx):  # type: ignore[no-untyped-def]
        output = ctx.artifact_dir() / "PIEE-draft.docx"
        output.write_bytes(b"synthetic draft")
        (ctx.artifact_dir() / "PIEE-checks.json").write_text(
            json.dumps(
                {"untouched": ["toc", "body_1"], "package_issues": ["broken"], "leftover_parts": []}
            ),
            encoding="utf-8",
        )
        ctx.save_output(output, "PIEE-draft.docx")
        return StageOutcome()

    run_stage(workspace, job, "piee_generate", stage)
    for _ in subscribe(workspace, job):
        pass
    workflow = PieeWorkflow()
    readiness = workflow.readiness(workspace, job)
    assert {issue.code for issue in readiness.blocking} >= {"untouched_anchor", "package"}
    assert workflow.render(workspace, job, "draft")
    with pytest.raises(EmaError) as wrong_kind:
        workflow.render(workspace, job, "unknown")
    assert wrong_kind.value.code == "output_kind"
    with pytest.raises(EmaError) as final:
        workflow.render(workspace, job, "final")
    assert final.value.code == "not_ready"
    snapshot = workflow.readiness_snapshot(workspace, job)
    assert snapshot["checks"]["untouched"] == ["toc", "body_1"]
