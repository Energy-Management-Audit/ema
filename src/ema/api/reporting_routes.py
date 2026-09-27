"""Reporting run HTTP adapters."""

from fastapi import FastAPI
from pydantic import BaseModel

from ema.api.models import ReportingIn, ReportingRun
from ema.core.workspace import Workspace
from ema.reporting import runs


class PreviewMeasure(BaseModel):
    description: str
    saving_tep: float | None
    cost_thousand_lei: float | None


class PreviewRow(BaseModel):
    nr: int
    beneficiary: str
    client_id: str
    measures: list[PreviewMeasure]


class ReportingPreview(BaseModel):
    years: list[int]
    read: int
    companies_per_year: dict[str, int]
    rows: dict[str, list[PreviewRow]]


def install_reporting_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/reporting/runs", tags=["reporting"], response_model=list[ReportingRun])
    def list_reporting_runs() -> list[dict[str, object]]:
        return runs.list_runs(ws)

    @app.post("/reporting/runs", tags=["reporting"], response_model=ReportingRun, status_code=202)
    def start(body: ReportingIn) -> dict[str, object]:
        return runs.start_run(ws, body.years, body.client_ids)

    @app.get("/reporting/runs/{run_id}", tags=["reporting"], response_model=ReportingRun)
    def get(run_id: str) -> dict[str, object]:
        return runs.get_run(ws, run_id)

    @app.get(
        "/reporting/runs/{run_id}/preview", tags=["reporting"], response_model=ReportingPreview
    )
    def preview(run_id: str) -> dict[str, object]:
        return runs.preview(ws, run_id)
