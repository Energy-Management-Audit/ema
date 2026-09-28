"""Thin HTTP adapters to shared job and review use cases."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any, Literal

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from ema.api.job_routes import validate_slot
from ema.api.models import (
    CancelResult,
    DeleteResult,
    ExportChecks,
    ExportResult,
    Job,
    JobStatus,
    NewJobResult,
    SectionState,
    SlotVersion,
)
from ema.api.provisional import install_provisional_routes
from ema.api.workflows import workflow_for
from ema.audit.render_bindings import COVER_SLOT, checked_photo
from ema.audit.sections import Status, set_status, statuses
from ema.clients.registry import get_client
from ema.core.errors import EmaError
from ema.core.jobs import cancel, create_job, get_job, list_jobs, status
from ema.core.jobs.events import replay
from ema.core.jobs.outputs import MEDIA
from ema.core.jobs.outputs import get_output as stored_output
from ema.core.review import (
    accept_batch,
    approve_final,
    conflicts,
    decide,
    export,
    fields,
    log,
    output_path,
    readiness_hash,
    undo,
)
from ema.core.review.evidence import get_evidence
from ema.core.review.models import Approval, Decision, Evidence, Field
from ema.core.review.readiness import approvals, readiness_hash_in_tx
from ema.core.workspace import Workspace


class NewJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["invoices", "piee", "audit", "reporting"]
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


class ExportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    final: Literal[True]
    output_id: str
    readiness_hash: str
    confirm: bool = False


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
        if body.type != "reporting":
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
        get_job(ws, job_id)
        with ws.connect() as db:
            rows = db.execute(
                "SELECT v.*,s.revision AS slot_revision FROM slot_versions v "
                "JOIN slots s ON s.job_id=v.job_id AND s.name=v.slot "
                "WHERE v.job_id=? AND v.slot=? ORDER BY v.version",
                (job_id, slot),
            ).fetchall()
        return [dict(row) for row in rows]

    @app.put("/jobs/{job_id}/slots/{slot:path}", tags=["documents"], response_model=SlotVersion)
    def put_slot(job_id: str, slot: str, body: SlotInput) -> dict[str, object]:
        job = get_job(ws, job_id)
        validate_slot(str(job["type"]), slot)
        if slot == COVER_SLOT:
            checked_photo(ws.file_path(str(job["client_slug"]), body.file_sha))
        version, revision = ws.set_slot_with_revision(job_id, slot, body.file_sha)
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
        return get_evidence(ws, evidence_id).model_dump(mode="json")

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

    @app.get("/jobs/{job_id}/export/checks", tags=["export"], response_model=ExportChecks)
    def checks(job_id: str) -> dict[str, Any]:
        workflow = workflow_for(ws, job_id)
        readiness = workflow.readiness(ws, job_id)
        return {
            "readiness": readiness.model_dump(mode="json"),
            "readiness_hash": readiness_hash(ws, job_id, readiness, workflow),
        }

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
        if mock:
            get_job(ws, job_id)
            return Response(
                b"Synthetic output",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"X-Content-Type-Options": "nosniff"},
            )
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

    @app.post("/jobs/{job_id}/export", tags=["export"], response_model=ExportResult)
    def do_export(job_id: str, body: ExportInput, request: Request) -> dict[str, str]:
        if not body.confirm or not getattr(request.state, "human_session", False):
            raise EmaError("human_required", "Confirmarea umană este necesară.", "")
        workflow = workflow_for(ws, job_id)
        with ws.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job_row = db.execute(
                "SELECT state FROM jobs WHERE id=? AND deleted=0", (job_id,)
            ).fetchone()
            if job_row is None:
                raise EmaError("job_missing", "Lucrarea nu există.", "")
            if job_row["state"] == "running":
                raise EmaError("job_running", "Lucrarea rulează deja.", "")
            readiness_reader = getattr(workflow, "readiness_in_tx", None)
            readiness = (
                readiness_reader(ws, job_id, db)
                if readiness_reader is not None
                else workflow.readiness(ws, job_id)
            )
            if not readiness.final_ok:
                db.commit()  # Persist audit staleness before refusing the export.
                raise EmaError("not_ready", "Lucrarea nu este pregătită.", "")
            current_hash = readiness_hash_in_tx(ws, db, job_id, readiness, workflow)
            if body.readiness_hash != current_hash:
                raise EmaError("hash_mismatch", "Datele de pregătire nu corespund.", "")
            approve_final(ws, job_id, body.output_id, current_hash, "user", db=db)
        source = output_path(ws, job_id, body.output_id)
        destination = ws.root / "exports" / f"{job_id}-{body.output_id}{source.suffix}"
        destination.parent.mkdir(exist_ok=True)
        export(
            ws,
            job_id,
            workflow,
            final=True,
            dest=destination,
            actor="user",
            expected_output_id=body.output_id,
        )
        return {"output_id": body.output_id}

    install_provisional_routes(app, ws, mock=mock)
