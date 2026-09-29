"""Invoice extraction and the legacy workbook contract."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal

from ema.clients.registry import find_by_cui
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import (
    JobId,
    StageContext,
    StageOutcome,
    create_job,
    get_job,
    latest_ready_run,
    run_stage,
    status,
    subscribe,
)
from ema.core.jobs.reads import run_current
from ema.core.logging import write_event
from ema.core.review.models import Issue, Readiness
from ema.core.workspace import Workspace
from ema.core.workspace.export import copy_output
from ema.invoices.artifact import encode, exportable_drafts
from ema.invoices.batch_identity import KEY as BATCH_CLIENT_KEY
from ema.invoices.composition import build_invoice_processor
from ema.invoices.export.exporter import OpenpyxlWorkbookExporter
from ema.invoices.identity_review import (
    batch_client,
    confirm_client,
    raw_outcomes,
    readiness,
    resolved_outcomes,
)
from ema.invoices.models import IssueCode
from ema.invoices.outcomes import DocumentOutcome
from ema.invoices.pipeline import ProcessInvoiceFiles

__all__ = (
    "BatchResult",
    "batch_client",
    "confirm_client",
    "export",
    "extract_batch",
    "raw_outcomes",
    "readiness",
    "render",
    "resolved_outcomes",
    "run_batch",
    "start_workbook",
)


@dataclass(frozen=True)
class BatchResult:
    outcomes: list[dict[str, Any]]
    omitted: list[str]
    run_id: str
    client_notice: str
    workbook: Path | None
    job_id: str
    client_proposal: dict[str, Any] | None


def run_batch(ws: Workspace, client: str, sources: list[Path]) -> BatchResult:
    if not sources:
        raise EmaError("invoices_empty", "Dosarul nu conţine facturi PDF.", "")
    client = str(find_by_cui(ws, client)["id"])
    job = create_job(ws, "invoices", client, None)
    preflight_failures: list[tuple[int, DocumentOutcome]] = []
    for index, source in enumerate(sources, 1):
        try:
            sha = ws.add_file(client, source)
        except OSError as error:
            preflight_failures.append(
                (
                    index - 1,
                    ProcessInvoiceFiles.failure_outcome(
                        source, IssueCode.PDF_READ_FAILED, str(error)
                    ),
                )
            )
            continue
        ws.set_slot(job, f"invoices/{index:04d}", sha, origin=source.name)
    run = run_stage(
        ws, job, "invoices", partial(extract_batch, preflight_failures=preflight_failures)
    )
    for _event in subscribe(ws, job):
        pass
    result = status(ws, job)
    matching = next(item for item in result.runs if item["id"] == run)
    if matching["state"] != "ready":
        raise EmaError("invoices_failed", "Extracţia facturilor a eşuat.", str(matching["error"]))
    outcomes = raw_outcomes(ws, job)
    omitted = [item["source_path"] for item in outcomes if item["status"] != "exportable"]
    _, proposed = batch_client(ws, job)
    return BatchResult(
        outcomes=outcomes,
        omitted=omitted,
        run_id=run,
        client_notice="Clientul lotului nu este încă confirmat; exportul este blocat.",
        workbook=None,
        job_id=job,
        client_proposal=json.loads(proposed.to_json()) if proposed else None,
    )


def extract_batch(
    ctx: StageContext,
    *,
    preflight_failures: list[tuple[int, DocumentOutcome]] | None = None,
) -> StageOutcome:
    versions = ctx.read_slots("invoices")
    if not versions and not preflight_failures:
        raise EmaError("invoices_empty", "Nu există facturi de procesat.", ctx.job)
    client = str(get_job(ctx.ws, ctx.job)["client_slug"])
    paths = [ctx.ws.file_path(client, version.file_sha) for version in versions]
    source_names = [version.origin for version in versions]
    processor = build_invoice_processor(load_settings(ctx.ws))
    result = processor.execute(paths, source_names=source_names, cancelled=ctx.cancelled)
    outcomes = list(result.outcomes)
    sources: list[tuple[str | None, str | None]] = [
        (version.slot, version.file_sha) for version in versions
    ]
    for index, failure in preflight_failures or []:
        outcomes.insert(index, failure)
        sources.insert(index, (None, None))
    (ctx.artifact_dir() / "outcomes.json").write_text(encode(outcomes, sources), encoding="utf-8")
    failures: list[str] = []
    for outcome in outcomes:
        if outcome.status.value != "failed":
            continue
        detail = outcome.metadata.technical_detail or outcome.reason or "unknown error"
        failures.append(f"{outcome.source_filename}: {detail}")
        with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
            write_event(
                handle, "invoice_item_failed", source=outcome.source_filename, detail=detail
            )
    warnings = [
        f"{outcome.source_filename}: {outcome.status.value}"
        for outcome in outcomes
        if outcome.status.value not in {"failed", "exportable"}
    ]
    return StageOutcome(item_failures=failures, warnings=warnings)


def render(
    ws: Workspace,
    job: JobId,
    kind: Literal["draft", "final"],
    *,
    ctx: StageContext | None = None,
    name: str = "Facturi.xlsx",
) -> str | None:
    run = latest_ready_run(ws, job, "invoices")
    if run is None:
        raise EmaError("invoices_missing", "Extracţia facturilor lipseşte.", job)
    with ws.connect() as db:
        if not run_current(db, run):
            raise EmaError("invoices_stale", "Extracţia facturilor nu mai este actuală.", job)
        artifact = ws.artifact_dir(db, job, "invoices", run) / "outcomes.json"
        ws.job_path(db, job)
    checks = readiness(ws, job)
    if not checks.final_ok:
        raise EmaError("invoices_unconfirmed_client", checks.blocking[0], job)
    client_field, _ = batch_client(ws, job)
    if ctx is not None:
        ctx.read_slots("invoices")
        ctx.record_read("fields", client_field.id, client_field.revision)
    drafts = exportable_drafts(json.dumps(resolved_outcomes(ws, job), ensure_ascii=False))
    if not drafts:
        raise EmaError("invoices_no_export", "Nicio factură nu poate fi exportată.", job)
    with tempfile.TemporaryDirectory(dir=artifact.parent) as temporary_dir:
        temporary = Path(temporary_dir) / "workbook.xlsx"
        OpenpyxlWorkbookExporter(firm_name=load_settings(ws).firm_name).export(drafts, temporary)
        if ctx is not None:
            ctx.save_output(temporary, name, kind=kind)
            return None
        with ws.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not run_current(db, run):
                raise EmaError("invoices_stale", "Extracţia facturilor nu mai este actuală.", job)
            confirmed = db.execute(
                "SELECT revision,data FROM fields WHERE job_id=? AND key=?",
                (job, BATCH_CLIENT_KEY),
            ).fetchone()
            if (
                confirmed is None
                or confirmed["revision"] != client_field.revision
                or json.loads(confirmed["data"])["review"] not in {"accepted", "corrected"}
            ):
                raise EmaError(
                    "invoices_unconfirmed_client", "Clientul lotului nu este confirmat.", job
                )
            previous = db.execute(
                "SELECT COUNT(*) FROM outputs WHERE job_id=? AND run_id=? AND kind='draft'",
                (job, run),
            ).fetchone()[0]
            output_name = (
                name if previous == 0 else f"{Path(name).stem}-{previous + 1}{Path(name).suffix}"
            )
            output = ws.save_output(db, job, run, temporary, output_name)
            ws.record_outputs(db, job, run, [(output, kind)])
            row = db.execute(
                "SELECT id FROM outputs WHERE job_id=? AND run_id=? ORDER BY seq DESC LIMIT 1",
                (job, run),
            ).fetchone()
    assert row is not None
    return str(row["id"])


def start_workbook(ws: Workspace, job: JobId, *, on_revision: int | None = None) -> str:
    run = latest_ready_run(ws, job, "invoices")
    if run is None:
        raise EmaError("invoices_missing", "Extracţia facturilor lipseşte.", job)
    with ws.connect() as db:
        if not run_current(db, run):
            raise EmaError("invoices_stale", "Extracţia facturilor nu mai este actuală.", job)
    checks = readiness(ws, job)
    if not checks.final_ok:
        raise EmaError("invoices_unconfirmed_client", checks.blocking[0], job)

    def stage(ctx: StageContext) -> StageOutcome:
        render(ws, job, "final", ctx=ctx)
        return StageOutcome()

    return run_stage(ws, job, "invoices_workbook", stage, on_revision=on_revision)


def start_extract(ws: Workspace, job: str, *, on_revision: int | None = None) -> str:
    if not ws.list_slots(job, "invoices"):
        raise EmaError("not_ready", "Facturile lipsesc.", job)
    return run_stage(ws, job, "invoices", extract_batch, on_revision=on_revision)


def export(ws: Workspace, job: JobId, dest: Path | None = None) -> Path:
    run = start_workbook(ws, job)
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    if record["state"] != "ready":
        raise EmaError("invoices_failed", "Generarea registrului a eşuat.", str(record["error"]))
    with ws.connect() as db:
        row = db.execute(
            "SELECT relative_path FROM outputs WHERE job_id=? AND run_id=? "
            "AND kind='final' ORDER BY seq DESC LIMIT 1",
            (job, run),
        ).fetchone()
    if row is None:
        raise EmaError("output_missing", "Documentul lipseşte.", job)
    source = ws.path(str(row["relative_path"]))
    if dest is not None and dest != source:
        with ws.connect() as db:
            sha = db.execute(
                "SELECT sha FROM outputs WHERE relative_path=?", (row["relative_path"],)
            ).fetchone()[0]
        return copy_output(ws, str(row["relative_path"]), str(sha), dest)
    return source


class InvoiceWorkflow:
    def readiness(self, ws: Workspace, job: JobId) -> Readiness:
        checks = readiness(ws, job)
        issues = [Issue(code="not_ready", message=message) for message in checks.blocking]
        return Readiness(
            draft_ok=True,
            final_ok=checks.final_ok,
            blocking=issues,
            next=[issue.message for issue in issues],
        )

    def readiness_snapshot(self, ws: Workspace, job: JobId) -> dict[str, object]:
        return {
            "invoices_run": latest_ready_run(ws, job, "invoices"),
            "workbook_run": latest_ready_run(ws, job, "invoices_workbook"),
        }

    def render(self, ws: Workspace, job: JobId, kind: str) -> str:
        if kind == "draft":
            output_id = render(ws, job, "draft")
            assert output_id is not None
            return output_id
        with ws.connect() as db:
            row = db.execute(
                "SELECT id FROM outputs WHERE job_id=? AND kind='final' ORDER BY seq DESC LIMIT 1",
                (job,),
            ).fetchone()
        if row is None:
            raise EmaError("output_missing", "Documentul final lipseşte.", "")
        return str(row["id"])
