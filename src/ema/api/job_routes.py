"""Static stage dispatch and job output HTTP adapters."""

from __future__ import annotations

import re

from fastapi import FastAPI, Request
from pydantic import BaseModel, ConfigDict

from ema.api.models import (
    ConflictChoice,
    NaProposal,
    Output,
    RunStart,
    SectionPatch,
)
from ema.api.models import (
    SectionState as SectionStateModel,
)
from ema.audit.intake import audit_intake, select_checklist
from ema.audit.read import read_job
from ema.audit.sections import Status, set_status
from ema.audit.sections_bulk import patch_sections
from ema.core.errors import EmaError
from ema.core.jobs import get_job, run_stage
from ema.core.jobs.outputs import list_outputs
from ema.core.review import decide
from ema.core.review.models import Decision
from ema.core.workspace import Workspace
from ema.core.workspace.conversion import active_version
from ema.invoices import extract_batch, start_workbook
from ema.piee.review_workflow import start_word_render
from ema.piee.workflow import start_generate_for_job

_STAGES: dict[str, set[str]] = {
    "audit": {"intake", "read", "fill", "draft"},
    "piee": {"piee_generate", "piee_word"},
    "invoices": {"invoices", "invoices_workbook"},
    "reporting": set(),
}

_PIEE_SLOTS = {"anexa", "questionnaire", "prelucrare", "previous_piee"}


def validate_slot(job_type: str, slot: str) -> None:
    allowed = False
    if job_type == "piee":
        allowed = slot in _PIEE_SLOTS
    elif job_type == "invoices":
        allowed = re.fullmatch(r"invoices/[0-9]{4}", slot) is not None
    elif job_type == "audit":
        if slot == "anexa":
            allowed = True
        else:
            prefix, separator, tail = slot.partition("/")
            parts = tail.split("/") if separator else []
            allowed = (
                prefix in {"dossier", "visit"}
                and 1 <= len(parts) <= 3
                and all(
                    1 <= len(part) <= 255
                    and part not in {".", ".."}
                    and "\\" not in part
                    and all(ord(char) >= 32 for char in part)
                    for part in parts
                )
            )
    if not allowed:
        raise EmaError("invalid_slot", "Numele fișierului este invalid.", "")


class StageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    on_revision: int


def _check_revision(ws: Workspace, job: str, expected: int) -> None:
    with ws.connect() as db:
        row = db.execute(
            "SELECT revision,state FROM jobs WHERE id=? AND deleted=0", (job,)
        ).fetchone()
    if row is None:
        raise EmaError("job_missing", "Lucrarea nu există.", "")
    if row["revision"] != expected:
        raise EmaError("stale_revision", "Lucrarea s-a modificat.", "")
    if row["state"] == "running":
        raise EmaError("job_running", "Lucrarea rulează deja.", "")


def start_named_stage(  # noqa: C901
    ws: Workspace, job: str, stage: str, on_revision: int, *, human_session: bool = False
) -> str:
    record = get_job(ws, job)
    job_type = str(record["type"])
    if stage not in _STAGES[job_type]:
        raise EmaError("invalid_stage", "Etapa este invalidă.", "")
    if stage in {"fill", "draft"}:
        raise EmaError("provisional_contract", "Agentul de audit nu este disponibil.", "")
    if stage == "invoices_workbook" and not human_session:
        raise EmaError("human_required", "Confirmarea umană este necesară.", "")
    _check_revision(ws, job, on_revision)
    if stage in {"intake", "read"}:
        slots = [
            version
            for name in ws.list_slots(job, "dossier")
            if (version := active_version(ws, job, name)) is not None
        ]
        select_checklist(slots)
    if stage == "intake":
        return run_stage(ws, job, stage, audit_intake, on_revision=on_revision)
    if stage == "read":
        return run_stage(ws, job, stage, read_job, on_revision=on_revision)
    if stage == "piee_generate":
        return start_generate_for_job(ws, job, on_revision=on_revision)
    if stage == "piee_word":
        return start_word_render(ws, job, on_revision=on_revision)
    if stage == "invoices":
        if not ws.list_slots(job, "invoices"):
            raise EmaError("not_ready", "Facturile lipsesc.", "")
        return run_stage(ws, job, stage, extract_batch, on_revision=on_revision)
    if stage == "invoices_workbook":
        return start_workbook(ws, job, on_revision=on_revision)
    raise EmaError("invalid_stage", "Etapa este invalidă.", "")


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

    @app.post(
        "/jobs/{job_id}/sections/{section_id}/na-proposal",
        tags=["audit"],
        response_model=SectionStateModel,
    )
    def na_proposal(job_id: str, section_id: str, body: NaProposal) -> dict[str, object]:
        return set_status(
            ws,
            job_id,
            section_id,
            Status.NA_PROPOSED,
            "ema",
            body.reason,
            on_revision=body.on_revision,
        ).payload()
