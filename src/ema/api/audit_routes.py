"""Audit-specific read views over shared workflow use cases."""

from __future__ import annotations

from fastapi import FastAPI

from ema.audit.visit import VisitView, visit_view
from ema.core.workspace import Workspace


def install_audit_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/jobs/{job_id}/visit", tags=["audit"], response_model=VisitView)
    def get_visit(job_id: str) -> VisitView:
        return visit_view(ws, job_id)
