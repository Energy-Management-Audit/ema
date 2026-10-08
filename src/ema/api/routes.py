"""Thin HTTP adapters to shared job and review use cases."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any, Literal

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from ema.api.export_routes import install_export_routes
from ema.api.models import (
    CancelResult,
    DeleteResult,
    Job,
    JobStatus,
    NewJobResult,
    SectionState,
    SlotVersion,
)
from ema.api.provisional import install_provisional_routes
from ema.audit.draft_style import PREVIOUS_AUDIT_SLOT, checked_previous_audit
from ema.audit.render_bindings import COVER_SLOT, checked_photo
from ema.audit.sections import Status, refresh_staleness, set_status, statuses
from ema.clients.registry import get_client
from ema.core.errors import EmaError
from ema.core.jobs import cancel, create_job, get_job, list_jobs, status
from ema.core.jobs.events import replay
from ema.core.review import (
    accept_batch,
    conflicts,
    decide,
    fields,
    log,
    undo,
)
from ema.core.review.evidence import get_evidence_view
from ema.core.review.models import Decision, Evidence, Field
from ema.core.workspace import Workspace
from ema.core.workspace.slots import slot_versions, validate_slot


class NewJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["invoices", "piee", "audit"]
    client: str
    year: int | None = None


class SlotInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_sha: str


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accept", "correct", "reject", "choose"]
    on_revision: int
    value: Any = None
    alternative: str | None = None
    reason: str | None = None


class BatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[tuple[str, int]]


class SectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["done", "n/a", "later", "ready", "missing", "drafted"]
    on_revision: int
    reason: str | None = None
    confirm: bool = False


class DeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: bool
    on_revision: int


async def _poll_events() -> None:
    await asyncio.sleep(1)


def install_routes(app: FastAPI, ws: Workspace, *, mock: bool = False) -> None:  # noqa: C901, PLR0915
    def audit_only(job_id: str) -> None:
        if get_job(ws, job_id)["type"] != "audit":
            raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", "")

    @app.get("/jobs", tags=["jobs"], response_model=list[Job])
    def jobs() -> list[dict[str, Any]]:
        return list_jobs(ws)

    @app.post("/jobs", tags=["jobs"], response_model=NewJobResult)
    def new_job(body: NewJob) -> dict[str, str]:
        get_client(ws, body.client)
        return {"id": create_job(ws, body.type, body.client, body.year)}

    @app.get("/jobs/{job_id}", tags=["jobs"], response_model=Job)
    def job(job_id: str) -> dict[str, object]:
        return get_job(ws, job_id)

    @app.get("/jobs/{job_id}/status", tags=["jobs"], response_model=JobStatus)
    def job_status(job_id: str) -> dict[str, object]:
        result = asdict(status(ws, job_id))
        for run in result["runs"]:
            if run.get("error"):
                run["error"] = "Etapa a eşuat."
        return result

    @app.get(
        "/jobs/{job_id}/events",
        tags=["jobs"],
        response_class=StreamingResponse,
        responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    )
    def events(
        job_id: str,
        request: Request,
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        get_job(ws, job_id)
        raw = last_event_id
        if raw is not None and not re.fullmatch(r"[0-9]+", raw):
            raise EmaError("invalid_cursor", "Poziţia evenimentului este invalidă.", raw)
        try:
            cursor = int(raw) if raw is not None else 0
        except ValueError as exc:
            raise EmaError("invalid_cursor", "Poziţia evenimentului este invalidă.", "") from exc

        async def stream() -> AsyncIterator[str]:
            nonlocal cursor
            idle = 0
            while not await request.is_disconnected():
                batch, terminal = replay(ws, job_id, cursor)
                for event in batch:
                    cursor = event.seq
                    payload = asdict(event)
                    data = json.dumps(payload, ensure_ascii=False)
                    yield f"id: {event.seq}\nevent: {event.type}\ndata: {data}\n\n"
                if not batch and terminal:
                    return
                if batch:
                    idle = 0
                    continue
                await _poll_events()
                idle += 1
                if idle == 15:
                    yield ": keepalive\n\n"
                    idle = 0

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/jobs/{job_id}/cancel", tags=["jobs"], response_model=CancelResult)
    def cancel_job(job_id: str) -> dict[str, bool]:
        get_job(ws, job_id)
        cancel(ws, job_id)
        return {"cancelled": True}

    @app.delete("/jobs/{job_id}", tags=["jobs"], response_model=DeleteResult)
    def delete_job(job_id: str, body: DeleteInput, request: Request) -> dict[str, bool]:
        if not body.confirm or not getattr(request.state, "human_session", False):
            raise EmaError("human_required", "Confirmarea umană este necesară.", "")
        ws.delete_job(job_id, on_revision=body.on_revision)
        return {"deleted": True}

    @app.get("/jobs/{job_id}/slots", tags=["documents"])
    def slots(job_id: str) -> list[str]:
        get_job(ws, job_id)
        return ws.list_slots(job_id, "")

    @app.get(
        "/jobs/{job_id}/slots/{slot:path}/versions",
        tags=["documents"],
        response_model=list[SlotVersion],
    )
    def versions(job_id: str, slot: str) -> list[dict[str, object]]:
        return slot_versions(ws, job_id, slot)

    @app.put("/jobs/{job_id}/slots/{slot:path}", tags=["documents"], response_model=SlotVersion)
    def put_slot(job_id: str, slot: str, body: SlotInput) -> dict[str, object]:
        job = get_job(ws, job_id)
        validate_slot(str(job["type"]), slot)
        if slot == COVER_SLOT:
            checked_photo(ws.file_path(str(job["client_slug"]), body.file_sha))
        if slot == PREVIOUS_AUDIT_SLOT:
            checked_previous_audit(ws.file_path(str(job["client_slug"]), body.file_sha))
        version, revision = ws.set_slot_with_revision(job_id, slot, body.file_sha)
        if slot == PREVIOUS_AUDIT_SLOT:
            refresh_staleness(ws, job_id)
        return {**asdict(version), "slot_revision": revision}

    @app.delete(
        "/jobs/{job_id}/slots/{slot:path}/versions/{version}",
        tags=["documents"],
        response_model=DeleteResult,
    )
    def delete_version(
        job_id: str, slot: str, version: int, body: DeleteInput, request: Request
    ) -> dict[str, bool]:
        if not body.confirm or not getattr(request.state, "human_session", False):
            raise EmaError("human_required", "Confirmarea umană este necesară.", "")
        ws.remove_version(job_id, slot, version, on_revision=body.on_revision)
        return {"deleted": True}

    @app.get("/jobs/{job_id}/fields", tags=["review"], response_model=list[Field])
    def get_fields(
        job_id: str,
        status_filter: Literal[
            "pending",
            "uncertain",
            "accepted",
            "corrected",
            "rejected",
            "conflict",
            "missing",
            "needs_confirmation",
        ]
        | None = Query(None, alias="status"),
    ) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in fields(ws, job_id, status=status_filter)]

    @app.post("/jobs/{job_id}/fields/{field_id}/decide", tags=["review"], response_model=Decision)
    def decide_field(job_id: str, field_id: str, body: DecisionInput) -> dict[str, Any]:
        return decide(
            ws,
            job_id,
            field_id,
            body.action,
            body.on_revision,
            "user",
            value=body.value,
            alternative=body.alternative,
            reason=body.reason,
        ).model_dump(mode="json")

    @app.post("/jobs/{job_id}/fields/accept-batch", tags=["review"], response_model=list[Decision])
    def batch(job_id: str, body: BatchInput) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json") for item in accept_batch(ws, job_id, body.fields, "user")
        ]

    @app.get("/jobs/{job_id}/conflicts", tags=["review"], response_model=list[Field])
    def get_conflicts(job_id: str) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in conflicts(ws, job_id)]

    @app.get("/jobs/{job_id}/log", tags=["review"], response_model=list[Decision])
    def get_log(job_id: str) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in log(ws, job_id)]

    @app.post("/jobs/{job_id}/log/{decision_id}/undo", tags=["review"], response_model=Decision)
    def undo_decision(job_id: str, decision_id: str) -> dict[str, Any]:
        return undo(ws, job_id, decision_id, "user").model_dump(mode="json")

    @app.get("/evidence/{evidence_id}/quote", tags=["review"], response_model=Evidence)
    def evidence_quote(evidence_id: str) -> dict[str, Any]:
        evidence, name = get_evidence_view(ws, evidence_id)
        return evidence.model_copy(update={"file_name": name}).model_dump(mode="json")

    @app.get("/jobs/{job_id}/sections", tags=["audit"], response_model=list[SectionState])
    def get_sections(job_id: str) -> list[dict[str, object]]:
        audit_only(job_id)
        return [item.payload() for item in statuses(ws, job_id)]

    @app.patch("/jobs/{job_id}/sections/{section_id}", tags=["audit"], response_model=SectionState)
    def change_section(
        job_id: str, section_id: str, body: SectionInput, request: Request
    ) -> dict[str, object]:
        audit_only(job_id)
        if body.status in ("done", "n/a") and (
            not body.confirm or not getattr(request.state, "human_session", False)
        ):
            raise EmaError("human_required", "Confirmarea umană este necesară.", "")
        return set_status(
            ws,
            job_id,
            section_id,
            Status(body.status),
            "user",
            body.reason,
            on_revision=body.on_revision,
        ).payload()

    install_export_routes(app, ws)

    install_provisional_routes(app, ws, mock=mock)
