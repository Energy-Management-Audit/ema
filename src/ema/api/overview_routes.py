"""Cross-workflow job overview for the shared sidebar."""

from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel

from ema.api.workflows import workflow_for
from ema.core.errors import EmaError
from ema.core.jobs import activity
from ema.core.workspace import Workspace


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
        with ws.connect() as db:
            db.execute("BEGIN")
            updated = activity(db)
            rows = db.execute(
                "SELECT j.id,j.type,j.client_slug,c.name AS client_name,j.year,j.state,"
                "j.revision,j.created_at,"
                "(SELECT MAX(a.at) FROM approvals a WHERE a.job_id=j.id) AS approved_at,"
                "(SELECT COUNT(*) FROM outputs o WHERE o.job_id=j.id AND o.kind='final') "
                "AS final_outputs FROM jobs j LEFT JOIN clients c ON c.id=j.client_slug "
                "WHERE j.deleted=0 AND j.type!='reporting'"
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["updated_at"] = updated.get(str(item["id"]), str(item["created_at"]))
            final_outputs = item.pop("final_outputs")
            item["finalized"] = item["approved_at"] is not None or (
                item["type"] == "invoices" and final_outputs > 0
            )
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
