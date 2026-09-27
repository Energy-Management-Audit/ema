"""What the Raport Word screen reads: the newest draft and final render runs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from ema.audit.render import INPUTS, STAGES, Kind, RenderSummary
from ema.audit.render_steps import configured_base
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.jobs.reads import run_current
from ema.core.office.word_api import word_available
from ema.core.workspace import Workspace


@dataclass(frozen=True)
class ReportRunData:
    run_id: str
    state: str
    ended_at: str | None
    current: bool
    summary: RenderSummary | None
    docx_output_id: str | None
    pdf_output_id: str | None


@dataclass(frozen=True)
class AuditReportData:
    draft: ReportRunData | None
    final: ReportRunData | None
    word: bool


def render_current(ws: Workspace, db: sqlite3.Connection, job: str, stage: str, run: str) -> bool:
    """A render is current while nothing it read changed (fields, sections, slots) and it was
    made from the base files configured now."""
    if not run_current(db, run):
        return False
    path = ws.artifact_dir(db, job, stage, run) / INPUTS
    try:
        made_from = json.loads(path.read_text("utf-8"))
        return made_from == configured_base(load_settings(ws)).inputs
    except (OSError, ValueError, EmaError):
        return False


def newest_final(ws: Workspace, db: sqlite3.Connection, job: str) -> tuple[str, str, bool] | None:
    """(run, docx sha, current) of the newest final that was published."""
    row = db.execute(
        "SELECT o.run_id,o.sha FROM outputs o JOIN runs r ON r.id=o.run_id "
        "WHERE o.job_id=? AND r.stage=? AND o.kind='final' ORDER BY o.seq DESC LIMIT 1",
        (job, STAGES["final"]),
    ).fetchone()
    if row is None:
        return None
    run = str(row["run_id"])
    return run, str(row["sha"]), render_current(ws, db, job, STAGES["final"], run)


def _newest(ws: Workspace, job: str, kind: Kind) -> ReportRunData | None:
    stage = STAGES[kind]
    with ws.connect() as db:
        db.execute("BEGIN")
        run = db.execute(
            "SELECT id,state,ended_at FROM runs WHERE job_id=? AND stage=? "
            "ORDER BY started_at DESC LIMIT 1",
            (job, stage),
        ).fetchone()
        if run is None:
            return None
        outputs = db.execute(
            "SELECT id,relative_path FROM outputs WHERE run_id=? ORDER BY seq", (run["id"],)
        ).fetchall()
        current = render_current(ws, db, job, stage, str(run["id"]))
        folder = ws.artifact_dir(db, job, stage, str(run["id"]))
    by_suffix = {str(row["relative_path"]).rsplit(".", 1)[-1]: str(row["id"]) for row in outputs}
    path = folder / "render.json"
    summary = RenderSummary.model_validate_json(path.read_text("utf-8")) if path.is_file() else None
    return ReportRunData(
        run_id=str(run["id"]),
        state=str(run["state"]),
        ended_at=run["ended_at"],
        current=current,
        summary=summary,
        docx_output_id=by_suffix.get("docx"),
        pdf_output_id=by_suffix.get("pdf"),
    )


def audit_report(ws: Workspace, job: str) -> AuditReportData:
    if get_job(ws, job)["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    return AuditReportData(
        draft=_newest(ws, job, "draft"),
        final=_newest(ws, job, "final"),
        word=word_available(load_settings(ws)),
    )
