"""PIEE HTTP review and generation adapters."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from ema.api.models import (
    Measure,
    PieeDataView,
    PieeGenerate,
    PieeImport,
    PieeSummary,
    PrelucrareInput,
    PrelucrareState,
    RunStart,
)
from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.workspace import Workspace
from ema.piee import views
from ema.piee.workflow import set_prelucrare
from ema.workflows_registry import start_named_stage


class DraftInput(BaseModel):
    on_revision: int


class DraftOutput(BaseModel):
    output_id: str
    kind: str


def install_piee_routes(app: FastAPI, ws: Workspace) -> None:
    def piee_only(job_id: str) -> None:
        if get_job(ws, job_id)["type"] != "piee":
            raise EmaError("wrong_job_type", "Lucrarea nu este PIEE.", "")

    @app.get("/jobs/{job_id}/measures", tags=["piee"], response_model=list[Measure])
    def measures(job_id: str) -> list[dict[str, object]]:
        return views.list_measures(ws, job_id)

    @app.get("/jobs/{job_id}/piee/data", tags=["piee"], response_model=PieeDataView)
    def data(job_id: str) -> dict[str, object]:
        return views.data(ws, job_id)

    @app.post("/jobs/{job_id}/piee/import", tags=["piee"], response_model=RunStart, status_code=202)
    def read_documents(job_id: str, body: PieeImport) -> dict[str, str]:
        piee_only(job_id)
        run = start_named_stage(ws, job_id, "piee_import", body.on_revision)
        return {"run_id": run, "stage": "piee_import", "state": "running"}

    @app.get("/jobs/{job_id}/piee/summary", tags=["piee"], response_model=PieeSummary)
    def piee_summary(job_id: str) -> dict[str, object]:
        return views.summary(ws, job_id)

    @app.post(
        "/jobs/{job_id}/piee/generate", tags=["piee"], response_model=RunStart, status_code=202
    )
    def generate(job_id: str, body: PieeGenerate) -> dict[str, str]:
        piee_only(job_id)
        run = start_named_stage(ws, job_id, "piee_generate", body.on_revision)
        return {"run_id": run, "stage": "piee_generate", "state": "running"}

    @app.get("/jobs/{job_id}/prelucrare", tags=["piee"], response_model=PrelucrareState)
    def prelucrare(job_id: str) -> dict[str, object]:
        return views.prelucrare_state(ws, job_id)

    @app.post("/jobs/{job_id}/prelucrare", tags=["piee"], response_model=PrelucrareState)
    def bind_prelucrare(job_id: str, body: PrelucrareInput) -> dict[str, object]:
        return set_prelucrare(ws, job_id, body.file_id, body.role)
