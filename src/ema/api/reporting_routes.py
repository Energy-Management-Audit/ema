"""Reporting run HTTP adapters."""

from fastapi import FastAPI

from ema.api.models import ReportingIn, ReportingRun
from ema.core.workspace import Workspace
from ema.reporting import runs


def install_reporting_routes(app: FastAPI, ws: Workspace) -> None:
    @app.post("/reporting/runs", tags=["reporting"], response_model=ReportingRun, status_code=202)
    def start(body: ReportingIn) -> dict[str, object]:
        return runs.start_run(ws, body.years, body.client_ids)

    @app.get("/reporting/runs/{run_id}", tags=["reporting"], response_model=ReportingRun)
    def get(run_id: str) -> dict[str, object]:
        return runs.get_run(ws, run_id)
