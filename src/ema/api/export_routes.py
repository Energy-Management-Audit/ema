"""HTTP adapters for checks, immutable downloads and final delivery."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

from ema.api.models import ExportChecks, ExportResponse
from ema.core.errors import EmaError
from ema.core.jobs.outputs import MEDIA
from ema.core.jobs.outputs import get_output as stored_output
from ema.core.review import export_final
from ema.core.review.final_export import default_export_folder
from ema.core.review.models import Approval
from ema.core.review.readiness import approvals, final_checks
from ema.core.workspace import Workspace
from ema.workflows_registry import workflow_for


class ExportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_id: str
    readiness_hash: str
    confirm: StrictBool
    dest_dir: Path | None

    @field_validator("dest_dir")
    @classmethod
    def valid_destination(cls, value: Path | None) -> Path | None:
        if value is not None and "\0" in str(value):
            raise ValueError("path contains a null byte")
        return value


def install_export_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/jobs/{job_id}/export/checks", tags=["export"], response_model=ExportChecks)
    def checks(job_id: str) -> dict[str, Any]:
        return final_checks(ws, job_id, workflow_for(ws, job_id))

    @app.get(
        "/jobs/{job_id}/outputs/{output_id}",
        tags=["export"],
        response_class=Response,
        responses={
            200: {
                "content": {
                    media: {"schema": {"type": "string", "format": "binary"}}
                    for media in MEDIA.values()
                },
            }
        },
    )
    def get_output(job_id: str, output_id: str) -> Response:
        metadata, relative = stored_output(ws, job_id, output_id)
        path = ws.path(relative)
        return FileResponse(
            path,
            filename=str(metadata["download_name"]),
            media_type=str(metadata["media_type"]),
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/jobs/{job_id}/approvals", tags=["export"], response_model=list[Approval])
    def job_approvals(job_id: str) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in approvals(ws, job_id)]

    @app.post("/jobs/{job_id}/export", tags=["export"], response_model=ExportResponse)
    def do_export(job_id: str, body: ExportInput, request: Request) -> dict[str, Any]:
        if not body.confirm or not getattr(request.state, "human_session", False):
            raise EmaError("human_required", "Confirmarea umană este necesară.", job_id)
        workflow = workflow_for(ws, job_id)
        result = export_final(
            ws,
            job_id,
            body.output_id,
            body.readiness_hash,
            body.dest_dir or default_export_folder(ws, job_id),
            workflow=workflow,
        )
        return result.model_dump(mode="json")
