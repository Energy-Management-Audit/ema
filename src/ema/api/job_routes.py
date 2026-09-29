"""Static stage dispatch and job output HTTP adapters."""

from __future__ import annotations

from fastapi import FastAPI, Request
from pydantic import BaseModel, ConfigDict

from ema.api.models import (
    ConflictChoice,
    Output,
    RunStart,
    SectionPatch,
)
from ema.api.models import (
    SectionState as SectionStateModel,
)
from ema.audit.sections_bulk import patch_sections
from ema.core.errors import EmaError
from ema.core.jobs.outputs import list_outputs
from ema.core.review import decide
from ema.core.review.models import Decision
from ema.core.workspace import Workspace
from ema.workflows_registry import start_named_stage


class StageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on_revision: int


def install_job_routes(app: FastAPI, ws: Workspace) -> None:
    @app.post(
        "/jobs/{job_id}/stages/{stage}",
        tags=["jobs"],
        response_model=RunStart,
        status_code=202,
        description=(
            "Bound stages start real runs. fill and draft return 501 because "
            "live audit agents do not exist (S14 has replay only)."
        ),
    )
    def start_stage(job_id: str, stage: str, body: StageInput, request: Request) -> dict[str, str]:
        run = start_named_stage(
            ws,
            job_id,
            stage,
            body.on_revision,
            human_session=getattr(request.state, "human_session", False),
        )
        return {"run_id": run, "stage": stage, "state": "running"}

    @app.get("/jobs/{job_id}/outputs", tags=["export"], response_model=list[Output])
    def outputs(job_id: str) -> list[dict[str, object]]:
        return list_outputs(ws, job_id)

    @app.post("/jobs/{job_id}/conflicts/{conflict_id}", tags=["review"], response_model=Decision)
    def choose_conflict(job_id: str, conflict_id: str, body: ConflictChoice) -> dict[str, object]:
        return decide(
            ws,
            job_id,
            conflict_id,
            "choose",
            body.on_revision,
            "user",
            alternative=body.candidate_id,
        ).model_dump(mode="json")

    @app.patch("/jobs/{job_id}/sections", tags=["audit"], response_model=list[SectionStateModel])
    def bulk_sections(
        job_id: str, body: list[SectionPatch], request: Request
    ) -> list[dict[str, object]]:
        if any(item.status in {"done", "n/a"} for item in body) and not getattr(
            request.state, "human_session", False
        ):
            raise EmaError("human_required", "Confirmarea umană este necesară.", "")
        return [
            item.payload()
            for item in patch_sections(ws, job_id, [item.model_dump() for item in body])
        ]
