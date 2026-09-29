"""Review readiness and approval-bound export for PIEE jobs."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import cast

from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, run_stage, status, subscribe
from ema.core.jobs.reads import run_current
from ema.core.office.anchors import leftover_issues
from ema.core.office.package import check_standalone
from ema.core.office.word_api import word_automation, word_available
from ema.core.review import base_readiness, fields
from ema.core.review.models import Field, FieldSpec, Issue, Readiness
from ema.core.workspace import Workspace
from ema.piee.annual_check import months_check
from ema.piee.compose import load_approved_base
from ema.piee.identity import percent_text
from ema.piee.workflow import base_directory, current_import


def _latest_draft(ws: Workspace, job: str) -> tuple[str, str, Path]:
    with ws.connect() as db:
        row = db.execute(
            "SELECT o.id,o.run_id,o.relative_path FROM outputs o "
            "JOIN runs r ON r.id=o.run_id WHERE o.job_id=? AND o.kind='draft' "
            "AND r.stage='piee_generate' ORDER BY o.seq DESC LIMIT 1",
            (job,),
        ).fetchone()
    if row is None:
        raise EmaError("piee_output_missing", "Ciorna PIEE lipseşte.", job)
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
        raise EmaError("piee_workbook_missing", "Prelucrare date lipseşte.", job)
    return ws.path(str(row["relative_path"]))


def _months_issues(job_fields: list[Field]) -> list[Issue]:
    by_key = {field.key: field for field in job_fields}
    readings = {
        field.key: (field.value, field.unit)
        for field in job_fields
        if field.key.startswith("carrier.")
        and isinstance(field.value, Decimal)
        and field.review != "rejected"
    }
    return [
        Issue(
            code="months_annual_mismatch",
            field_id=by_key[item.annual_key].id,
            message="Suma lunilor nu se potriveşte cu totalul anual.",
        )
        for item in months_check(readings)
    ]


def _ownership_issues(job_fields: list[Field]) -> list[Issue]:
    return [
        Issue(code="missing", field_id=field.id, message=f"Lipseşte: {field.label}")
        for field in job_fields
        if field.key in {"identity.ownership_state", "identity.ownership_private"}
        and (field.review == "rejected" or percent_text(str(field.value)) is None)
    ]


def _payback_issues(job_fields: list[Field]) -> list[Issue]:
    by_key = {field.key: field for field in job_fields}
    issues: list[Issue] = []
    for field in job_fields:
        if (
            field.key.startswith("measure.")
            and field.key.endswith(".payback_years")
            and field.state == "calculated"
            and field.review == "pending"
            and field.presence == "found"
        ):
            description = by_key.get(field.key.removesuffix("payback_years") + "description")
            measure = str(description.value) if description and description.value else field.label
            issues.append(
                Issue(
                    code="calculated_unconfirmed",
                    field_id=field.id,
                    message=f"Confirmaţi durata de recuperare calculată: {measure}",
                )
            )
    return issues


def _wait_for_output(ws: Workspace, job: str, run: str) -> str:
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    if record["state"] != "ready":
        raise EmaError(
            "piee_word_failed", "Finalizarea PIEE în Word a eşuat.", str(record["error"])
        )
    with ws.connect() as db:
        row = db.execute(
            "SELECT id FROM outputs WHERE job_id=? AND run_id=? AND kind='final'",
            (job, run),
        ).fetchone()
    if row is None:
        raise EmaError("piee_output_missing", "Documentul PIEE final lipseşte.", run)
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
        job_fields = fields(ws, job)
        issues = [
            *base.blocking,
            *_months_issues(job_fields),
            *_payback_issues(job_fields),
            *_ownership_issues(job_fields),
        ]
        if current_import(ws, job) is None:
            issues.append(
                Issue(code="import_required", message="Documentele trebuie citite din nou.")
            )
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
            issues.append(Issue(code="draft_missing", message=f"Ciorna PIEE lipseşte: {exc}"))
        return Readiness(
            draft_ok=True,
            final_ok=not issues,
            blocking=issues,
            next=[item.message for item in issues],
        )

    def readiness_snapshot(self, ws: Workspace, job: str) -> dict[str, object]:
        try:
            _, run, output = _latest_draft(ws, job)
        except EmaError as exc:
            if exc.code != "piee_output_missing":
                raise
            return {"run": None}
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
    """Start the final Word stage without waiting for Word automation."""
    _, draft_run, draft_path = _latest_draft(ws, job)
    if not PieeWorkflow().readiness(ws, job).final_ok:
        raise EmaError("not_ready", "Lucrarea nu este pregătită pentru export.", job)
    settings = load_settings(ws)
    if not word_available(settings):
        raise EmaError("word_unavailable", "Microsoft Word nu este disponibil.", "")
    base_dir = base_directory(ws)
    mapping = load_approved_base(base_dir)
    workbook_path = _draft_workbook(ws, job, draft_run)

    def stage(ctx: StageContext) -> StageOutcome:
        ctx.read_slots("")
        original = ctx.artifact_dir() / "PIEE-final.docx"
        original.write_bytes(draft_path.read_bytes())
        office = word_automation(settings)
        office.update_toc_pages(original)
        pdf = ctx.artifact_dir() / "PIEE-final.pdf"
        office.render_pdf(original, pdf)
        office.open_check(original)
        issues = check_standalone(original)
        denylist = tuple(json.loads((base_dir / "base-identity.json").read_text(encoding="utf-8")))
        leftovers = leftover_issues(original, denylist)
        if issues or leftovers or not pdf.is_file() or not pdf.stat().st_size:
            raise EmaError("piee_package", "Pachetul PIEE final este invalid.", job)
        ctx.record_input(template=mapping.base_sha)
        ctx.save_output(workbook_path, "Prelucrare-date.xlsx")
        ctx.save_output(pdf, "PIEE-final.pdf")
        ctx.save_output(original, "PIEE-final.docx", kind="final")
        return StageOutcome()

    return run_stage(ws, job, "piee_word", stage, on_revision=on_revision)
