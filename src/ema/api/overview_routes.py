"""Cross-workflow job overview for the shared sidebar."""

from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel

from ema.core.errors import EmaError
from ema.core.review.overview import job_overview
from ema.core.workspace import Workspace
from ema.workflows_registry import workflow_for


class JobOverview(BaseModel):
    id: str
    type: Literal["invoices", "piee", "audit", "reporting"]
    client_slug: str
    client_name: str | None
    year: int | None
    state: str
    revision: int
    created_at: str
    updated_at: str
    final_ok: bool | None
    blocking: int | None
    next: str | None
    readiness_error: str | None
    approved_at: str | None
    finalized: bool


def install_overview_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/jobs/overview", tags=["jobs"], response_model=list[JobOverview])
    def overview() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in job_overview(ws):
            try:
                readiness = workflow_for(ws, str(item["id"])).readiness(ws, str(item["id"]))
            except EmaError as exc:
                item.update(final_ok=None, blocking=None, next=None, readiness_error=exc.code)
            else:
                item.update(
                    final_ok=readiness.final_ok,
                    blocking=len(readiness.blocking),
                    next=readiness.next[0] if readiness.next else None,
                    readiness_error=None,
                )
            result.append(item)
        return sorted(result, key=lambda item: item["updated_at"], reverse=True)
