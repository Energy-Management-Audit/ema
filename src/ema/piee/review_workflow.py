"""Review readiness and approval-bound export for PIEE jobs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, run_stage, status, subscribe
from ema.core.jobs.reads import run_current
from ema.core.office.anchors import leftover_issues
from ema.core.office.package import check_standalone
from ema.core.office.word import WordMac
from ema.core.review import base_readiness
from ema.core.review.models import FieldSpec, Issue, Readiness
from ema.core.workspace import Workspace
from ema.piee.compose import load_approved_base
from ema.piee.workflow import base_directory


def _latest_draft(ws: Workspace, job: str) -> tuple[str, str, Path]:
    with ws.connect() as db:
        row = db.execute(
            "SELECT o.id,o.run_id,o.relative_path FROM outputs o "
            "JOIN runs r ON r.id=o.run_id WHERE o.job_id=? AND o.kind='draft' "
            "AND r.stage='piee_generate' ORDER BY o.seq DESC LIMIT 1",
            (job,),
        ).fetchone()
    if row is None:
        raise EmaError("piee_output_missing", "Ciorna PIEE lipsește.", job)
    return str(row["id"]), str(row["run_id"]), ws.path(str(row["relative_path"]))


def _checks(ws: Workspace, job: str) -> dict[str, object]:
    _, run, _ = _latest_draft(ws, job)
    with ws.connect() as db:
        path = ws.artifact_dir(db, job, "piee_generate", run) / "PIEE-checks.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _draft_workbook(ws: Workspace, job: str, run: str) -> Path:
    with ws.connect() as db:
        row = db.execute(
            "SELECT relative_path FROM outputs WHERE job_id=? AND run_id=? "
            "AND relative_path LIKE '%.xlsx' LIMIT 1",
            (job, run),
        ).fetchone()
    if row is None:
        raise EmaError("piee_workbook_missing", "Prelucrare date lipsește.", job)
    return ws.path(str(row["relative_path"]))


def _wait_for_output(ws: Workspace, job: str, run: str) -> str:
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    if record["state"] != "ready":
        raise EmaError(
            "piee_word_failed", "Finalizarea PIEE în Word a eșuat.", str(record["error"])
        )
    with ws.connect() as db:
        row = db.execute(
            "SELECT id FROM outputs WHERE job_id=? AND run_id=? AND kind='final'",
            (job, run),
        ).fetchone()
    if row is None:
        raise EmaError("piee_output_missing", "Documentul PIEE final lipsește.", run)
    return str(row["id"])


class PieeWorkflow:
    """The CLI and API share these readiness and render use cases."""

    def readiness(self, ws: Workspace, job: str) -> Readiness:
        base = base_readiness(
            ws,
            job,
            [
                FieldSpec(key="identity.name", label="Denumire", value_type="text", required=True),
                FieldSpec(
                    key="annual.total_tep",
                    label="Date anuale total tep",
                    value_type="number",
                    required=True,
                ),
            ],
        )
        issues = list(base.blocking)
        try:
            checks = _checks(ws, job)
            _, draft_run, _ = _latest_draft(ws, job)
            with ws.connect() as db:
                if not run_current(db, draft_run):
                    issues.append(Issue(code="stale", message="Datele PIEE s-au schimbat."))
            base_dir = base_directory(ws)
            toc_slots = set(
                json.loads((base_dir / "toc-manifest.json").read_text(encoding="utf-8"))[
                    "number_slots"
                ]
            )
            untouched = set(cast("list[str]", checks["untouched"]))
            if untouched - toc_slots:
                issues.append(Issue(code="untouched_anchor", message="Câmpuri PIEE necompletate."))
            if checks["package_issues"] or checks["leftover_parts"]:
                issues.append(Issue(code="package", message="Pachetul Word PIEE este invalid."))
        except (EmaError, OSError, KeyError, ValueError) as exc:
            issues.append(Issue(code="draft_missing", message=f"Ciorna PIEE lipsește: {exc}"))
        return Readiness(
            draft_ok=True,
            final_ok=not issues,
            blocking=issues,
            next=[item.message for item in issues],
        )

    def readiness_snapshot(self, ws: Workspace, job: str) -> dict[str, object]:
        _, run, output = _latest_draft(ws, job)
        base_dir = base_directory(ws)
        return {
            "run": run,
            "sha": hashlib.sha256(output.read_bytes()).hexdigest(),
            "map_sha": hashlib.sha256((base_dir / "base-map.json").read_bytes()).hexdigest(),
            "checks": _checks(ws, job),
        }

    def render(self, ws: Workspace, job: str, kind: str) -> str:
        draft_id, _, _ = _latest_draft(ws, job)
        if kind == "draft":
            return draft_id
        if kind != "final":
            raise EmaError("output_kind", "Tipul documentului este invalid.", kind)
        return _wait_for_output(ws, job, start_word_render(ws, job))


def start_word_render(ws: Workspace, job: str, *, on_revision: int | None = None) -> str:
    """Start the final Word stage without waiting for WordMac."""
    _, draft_run, draft_path = _latest_draft(ws, job)
    if not PieeWorkflow().readiness(ws, job).final_ok:
        raise EmaError("not_ready", "Lucrarea nu este pregătită pentru export.", job)
    settings = load_settings(ws)
    if not settings.word_path.is_dir():
        raise EmaError("word_unavailable", "Microsoft Word nu este disponibil.", "")
    base_dir = base_directory(ws)
    mapping = load_approved_base(base_dir)
    workbook_path = _draft_workbook(ws, job, draft_run)

    def stage(ctx: StageContext) -> StageOutcome:
        ctx.read_slots("")
        original = ctx.artifact_dir() / "PIEE-final.docx"
        original.write_bytes(draft_path.read_bytes())
        office = WordMac(app=settings.word_path, timeout_s=settings.word_timeout_s)
        office.update_toc_pages(original)
        pdf = ctx.artifact_dir() / "PIEE-final.pdf"
        office.render_pdf(original, pdf)
        office.open_check(original)
        issues = check_standalone(original)
        denylist = tuple(json.loads((base_dir / "base-identity.json").read_text()))
        leftovers = leftover_issues(original, denylist)
        if issues or leftovers or not pdf.is_file() or not pdf.stat().st_size:
            raise EmaError("piee_package", "Pachetul PIEE final este invalid.", job)
        ctx.record_input(template=mapping.base_sha)
        ctx.save_output(workbook_path, "Prelucrare-date.xlsx")
        ctx.save_output(pdf, "PIEE-final.pdf")
        ctx.save_output(original, "PIEE-final.docx", kind="final")
        return StageOutcome()

    return run_stage(ws, job, "piee_word", stage, on_revision=on_revision)
