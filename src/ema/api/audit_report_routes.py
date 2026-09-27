"""The audit report view: the newest draft and final render of an audit job."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI
from pydantic import BaseModel

from ema.audit.render import RenderSummary
from ema.audit.render_report import audit_report
from ema.core.workspace import Workspace


class ReportRun(BaseModel):
    run_id: str
    state: str
    ended_at: str | None
    current: bool
    summary: RenderSummary | None
    docx_output_id: str | None
    pdf_output_id: str | None


class AuditReport(BaseModel):
    draft: ReportRun | None
    final: ReportRun | None
    word: bool


def install_audit_report_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/jobs/{job_id}/audit/report", tags=["audit"], response_model=AuditReport)
    def get_report(job_id: str) -> AuditReport:
        return AuditReport.model_validate(asdict(audit_report(ws, job_id)))
