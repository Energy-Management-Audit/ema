"""Invoice extraction and the legacy workbook contract."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

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
from ema.core.workspace import Workspace
from ema.invoices.artifact import encode, exportable_drafts
from ema.invoices.composition import build_invoice_processor
from ema.invoices.export.exporter import OpenpyxlWorkbookExporter
from ema.invoices.models import IssueCode
from ema.invoices.outcomes import DocumentOutcome
from ema.invoices.pipeline import ProcessInvoiceFiles


@dataclass(frozen=True)
class BatchResult:
    outcomes: list[dict[str, Any]]
    omitted: list[str]
    run_id: str
    client_notice: str
    workbook: Path | None


def run_batch(ws: Workspace, client: str, sources: list[Path]) -> BatchResult:
    if not sources:
        raise EmaError("invoices_empty", "Dosarul nu conține facturi PDF.", "")
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
        raise EmaError("invoices_failed", "Extracția facturilor a eșuat.", str(matching["error"]))
    with ws.connect() as db:
        artifact = ws.artifact_dir(db, job, "invoices", run) / "outcomes.json"
        output_dir = ws.job_path(db, job) / "outputs"
    outcomes = json.loads(artifact.read_text(encoding="utf-8"))
    omitted = [item["source_path"] for item in outcomes if item["status"] != "exportable"]
    workbook = (
        export(ws, job, output_dir / "Facturi.xlsx") if len(omitted) < len(outcomes) else None
    )
    return BatchResult(
        outcomes=outcomes,
        omitted=omitted,
        run_id=run,
        client_notice=(
            "Clientul lotului nu este încă confirmat; exportul folosește identificarea actuală."
        ),
        workbook=workbook,
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
    result = processor.execute(paths, source_names=source_names)
    outcomes = list(result.outcomes)
    for index, failure in preflight_failures or []:
        outcomes.insert(index, failure)
    (ctx.artifact_dir() / "outcomes.json").write_text(encode(outcomes), encoding="utf-8")
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


def export(ws: Workspace, job: JobId, dest: Path) -> Path:
    run = latest_ready_run(ws, job, "invoices")
    if run is None:
        raise EmaError("invoices_missing", "Extracția facturilor lipsește.", job)
    with ws.connect() as db:
        if not run_current(db, run):
            raise EmaError("invoices_stale", "Extracția facturilor nu mai este actuală.", job)
        artifact = ws.artifact_dir(db, job, "invoices", run) / "outcomes.json"
        output_dir = ws.job_path(db, job) / "outputs"
    if dest.parent.resolve() != output_dir.resolve():
        raise EmaError("output_path", "Exportul trebuie salvat în lucrare.", str(dest))
    drafts = exportable_drafts(artifact.read_text(encoding="utf-8"))
    if not drafts:
        raise EmaError("invoices_no_export", "Nicio factură nu poate fi exportată.", job)
    with tempfile.TemporaryDirectory(dir=artifact.parent) as temporary_dir:
        temporary = Path(temporary_dir) / "workbook.xlsx"
        OpenpyxlWorkbookExporter().export(drafts, temporary)
        with ws.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not run_current(db, run):
                raise EmaError("invoices_stale", "Extracția facturilor nu mai este actuală.", job)
            output = ws.save_output(db, job, run, temporary, dest.name)
            ws.record_outputs(db, job, run, [(output, "draft")])
    return output
