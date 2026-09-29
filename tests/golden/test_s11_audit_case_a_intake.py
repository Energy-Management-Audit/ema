"""audit_case_a dossier completeness against its own checklist (evidence level 1)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from tests.golden.cases import case_path
from tests.workspace_jobs import create_job

from ema.audit.intake import audit_intake
from ema.core.jobs import run_stage, status, subscribe
from ema.core.workspace import Workspace

pytestmark = [pytest.mark.golden, pytest.mark.word]


def test_audit_case_a_intake_is_complete_and_uses_no_ai(tmp_path: Path) -> None:
    root = Path(os.environ["EMA_REFERENCE"]) / case_path("audit-case-a", "received")
    sources = sorted(path for path in root.iterdir() if path.is_file())
    assert len(sources) == 27
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "audit_case_a-golden", 2026)
    for source in sources:
        ws.set_slot(job, f"dossier/{source.name}", ws.add_file("audit_case_a-golden", source))
    run = run_stage(ws, job, "audit_intake", audit_intake)
    for _ in subscribe(ws, job):
        pass
    record = next(row for row in status(ws, job).runs if row["id"] == run)
    assert record["state"] == "ready", record["error"]
    with ws.connect() as db:
        report_path = ws.artifact_dir(db, job, "audit_intake", run) / "completeness.json"
        call_count = db.execute("SELECT count(*) FROM llm_calls WHERE job_id=?", (job,)).fetchone()[
            0
        ]
    assert call_count == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert len(report["checklist"]) == 13
    assert len(report["files"]) == 27
    assert report["missing"] == [1, 3, 6, 10]
    assert {int(number): len(names) for number, names in report["received"].items()} == {
        1: 0,
        2: 2,
        3: 0,
        4: 2,
        5: 7,
        6: 0,
        7: 1,
        8: 2,
        9: 3,
        10: 0,
        11: 1,
        12: 2,
        13: 6,
    }
    assert report["unclassified"] == []
    assert report["visit_material"] == []
    assert sum(file["status"] == "converted" for file in report["files"]) == 7
    assert all(file["status"] not in {"failed", "needs_conversion"} for file in report["files"])
