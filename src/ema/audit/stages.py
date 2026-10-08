"""Audit job intake and stage starters shared by interfaces."""

from __future__ import annotations

from pathlib import Path

from ema.audit.chapter_five import start_measurements
from ema.audit.draft_live import start_draft
from ema.audit.draft_style import PREVIOUS_AUDIT_SLOT
from ema.audit.fill_stage import start_fill
from ema.audit.intake import audit_intake, select_checklist
from ema.audit.measures import compose_measures, validate_measures_form
from ema.audit.read import read_job
from ema.audit.render import start_audit_render
from ema.audit.render_bindings import checked_photo
from ema.audit.research_stage import start_research
from ema.audit.visit import start_visit
from ema.audit.workflow import AuditWorkflow
from ema.clients.registry import find_by_cui
from ema.core.errors import EmaError
from ema.core.jobs import create_job, get_job, run_stage
from ema.core.office.sniff import FileKind, sniff
from ema.core.workspace import Workspace, upload_name
from ema.core.workspace.conversion import active_version
from ema.core.workspace.slots import validate_slot


def new_audit(ws: Workspace, cui: str, year: int) -> str:
    return create_job(ws, "audit", str(find_by_cui(ws, cui)["id"]), year)


def add_document(ws: Workspace, job: str, source: Path, slot: str | None = None) -> int:
    record = get_job(ws, job)
    if record["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    target = slot or f"dossier/{source.name}"
    validate_slot("audit", target)
    if not source.is_file():
        raise EmaError("file_missing", "Fişierul nu există.", str(source))
    if target == "cover/photo":
        checked_photo(source)
    if target == PREVIOUS_AUDIT_SLOT and sniff(source).kind != FileKind.DOCX:
        raise EmaError(
            "previous_audit_type", "Auditul anterior nu este un document Word .docx.", source.name
        )
    sha = ws.add_file(str(record["client_slug"]), source)
    return ws.set_slot(job, target, sha, original_name=upload_name(source.name)).version


def start_audit_stage(ws: Workspace, job: str, stage: str, on_revision: int) -> str:
    record = get_job(ws, job)
    if record["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    if record["state"] == "running":
        raise EmaError("job_running", "Lucrarea rulează deja.", job)
    if record["revision"] != on_revision:
        raise EmaError("stale_revision", "Lucrarea s-a modificat.", job)
    if stage == "readings":
        raise EmaError("ai_client_disabled", "Citirea fotografiilor aşteaptă aprobarea.", stage)
    if stage in {"intake", "read"}:
        versions = [
            version
            for name in ws.list_slots(job, "dossier")
            if (version := active_version(ws, job, name)) is not None
        ]
        select_checklist(versions)
        return run_stage(
            ws, job, stage, audit_intake if stage == "intake" else read_job, on_revision=on_revision
        )
    if starter := {
        "fill": start_fill,
        "draft": start_draft,
        "visit": start_visit,
        "measurements": start_measurements,
        "research": start_research,
        "audit_final": AuditWorkflow().start_final,
    }.get(stage):
        return starter(ws, job, on_revision=on_revision)
    if stage == "measures":
        validate_measures_form(ws, job)
        return run_stage(ws, job, stage, compose_measures, on_revision=on_revision)
    if stage == "audit_render":
        return start_audit_render(ws, job, "draft", on_revision=on_revision)
    raise EmaError("invalid_stage", "Etapa este invalidă.", stage)
