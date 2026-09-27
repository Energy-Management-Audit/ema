"""Audit-specific read views over shared workflow use cases."""

from __future__ import annotations

from fastapi import FastAPI

from ema.api.models import AuditDeadlineInput, AuditDeadlineResult, AuditNoteInput, AuditNoteResult
from ema.audit.annotations import put_deadline, put_note
from ema.audit.documents import AuditDocuments, documents
from ema.audit.outline import AuditOutline, outline
from ema.audit.visit import VisitView, visit_view
from ema.core.workspace import Workspace


def install_audit_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/jobs/{job_id}/audit/documents", tags=["audit"], response_model=AuditDocuments)
    def get_documents(job_id: str) -> AuditDocuments:
        return documents(ws, job_id)

    @app.get("/jobs/{job_id}/audit/outline", tags=["audit"], response_model=AuditOutline)
    def get_outline(job_id: str) -> AuditOutline:
        return outline(ws, job_id)

    @app.put(
        "/jobs/{job_id}/audit/notes/{section_id}",
        tags=["audit"],
        response_model=AuditNoteResult,
    )
    def update_note(job_id: str, section_id: str, body: AuditNoteInput) -> dict[str, str | int]:
        return put_note(ws, job_id, section_id, body.text, body.on_revision)

    @app.put("/jobs/{job_id}/audit/deadline", tags=["audit"], response_model=AuditDeadlineResult)
    def update_deadline(job_id: str, body: AuditDeadlineInput) -> dict[str, str | int | None]:
        return put_deadline(ws, job_id, body.deadline, body.on_revision)

    @app.get("/jobs/{job_id}/visit", tags=["audit"], response_model=VisitView)
    def get_visit(job_id: str) -> VisitView:
        return visit_view(ws, job_id)
