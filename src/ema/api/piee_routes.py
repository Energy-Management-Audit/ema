"""PIEE HTTP review and generation adapters."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from ema.api.job_routes import start_named_stage
from ema.api.models import (
    Measure,
    PieeDataView,
    PieeGenerate,
    PrelucrareInput,
    PrelucrareState,
    RunStart,
)
from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.workspace import Workspace
from ema.invoices import render as render_invoice
from ema.piee import views
from ema.piee.review_workflow import PieeWorkflow
from ema.piee.workflow import set_prelucrare


class DraftInput(BaseModel):
    on_revision: int


class DraftOutput(BaseModel):
    output_id: str
    kind: str


def install_piee_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/jobs/{job_id}/measures", tags=["piee"], response_model=list[Measure])
    def measures(job_id: str) -> list[dict[str, object]]:
        return views.list_measures(ws, job_id)

    @app.get("/jobs/{job_id}/piee/data", tags=["piee"], response_model=PieeDataView)
    def data(job_id: str) -> dict[str, object]:
        return views.data(ws, job_id)

    @app.post(
        "/jobs/{job_id}/piee/generate", tags=["piee"], response_model=RunStart, status_code=202
    )
    def generate(job_id: str, body: PieeGenerate) -> dict[str, str]:
        run = start_named_stage(ws, job_id, "piee_generate", body.on_revision)
        return {"run_id": run, "stage": "piee_generate", "state": "running"}

    @app.get("/jobs/{job_id}/prelucrare", tags=["piee"], response_model=PrelucrareState)
    def prelucrare(job_id: str) -> dict[str, object]:
        return views.prelucrare_state(ws, job_id)

    @app.post("/jobs/{job_id}/prelucrare", tags=["piee"], response_model=PrelucrareState)
    def bind_prelucrare(job_id: str, body: PrelucrareInput) -> dict[str, object]:
        return set_prelucrare(ws, job_id, body.file_id, body.role)

    @app.post("/jobs/{job_id}/export/draft", tags=["export"], response_model=DraftOutput)
    def draft(job_id: str, body: DraftInput) -> dict[str, str]:
        record = get_job(ws, job_id)
        if record["type"] == "audit":
            raise EmaError("audit_render_unavailable", "Redarea auditului nu este disponibilă.", "")
        if record["type"] not in {"piee", "invoices"}:
            raise EmaError("wrong_job_type", "Lucrarea este invalidă.", "")
        with ws.connect() as db:
            row = db.execute("SELECT revision FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or row["revision"] != body.on_revision:
            raise EmaError("stale_revision", "Lucrarea s-a modificat.", "")
        output = (
            PieeWorkflow().render(ws, job_id, "draft")
            if record["type"] == "piee"
            else render_invoice(ws, job_id, "draft")
        )
        assert output is not None
        return {"output_id": output, "kind": "draft"}
