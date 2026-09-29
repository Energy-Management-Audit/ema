"""Static workflow selection shared by every interface."""

from __future__ import annotations

from dataclasses import replace

from ema.audit.stages import start_audit_stage
from ema.audit.workflow import AuditWorkflow
from ema.clients.registry import find_by_cui
from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.review.readiness import Workflow
from ema.core.workspace import Workspace
from ema.invoices import InvoiceWorkflow, start_extract, start_workbook
from ema.piee.review_workflow import PieeWorkflow, start_word_render
from ema.piee.workflow import (
    GeneratedDraft,
    GenerateRequest,
    start_generate_for_job,
    start_import_for_job,
)
from ema.piee.workflow import generate_draft as _generate_draft


def workflow_for(ws: Workspace, job_id: str) -> Workflow:
    job_type = get_job(ws, job_id)["type"]
    if job_type == "audit":
        return AuditWorkflow()
    if job_type == "piee":
        return PieeWorkflow()
    if job_type == "invoices":
        return InvoiceWorkflow()
    raise EmaError("workflow_unavailable", "Fluxul de lucru nu este disponibil.", str(job_type))


def start_named_stage(
    ws: Workspace, job: str, stage: str, on_revision: int, *, human_session: bool = False
) -> str:
    kind = get_job(ws, job)["type"]
    if kind == "audit":
        return start_audit_stage(ws, job, stage, on_revision)
    if kind == "piee":
        starters = {
            "piee_import": start_import_for_job,
            "piee_generate": start_generate_for_job,
            "piee_word": start_word_render,
        }
        if starter := starters.get(stage):
            return starter(ws, job, on_revision=on_revision)
    if kind == "invoices":
        if stage == "invoices":
            return start_extract(ws, job, on_revision=on_revision)
        if stage == "invoices_workbook":
            if not human_session:
                raise EmaError("human_required", "Confirmarea umană este necesară.", job)
            return start_workbook(ws, job, on_revision=on_revision)
    raise EmaError("invalid_stage", "Etapa este invalidă.", stage)


def generate_draft(ws: Workspace, request: GenerateRequest) -> GeneratedDraft:
    client = find_by_cui(ws, request.client)
    return _generate_draft(ws, replace(request, client=str(client["id"])))
