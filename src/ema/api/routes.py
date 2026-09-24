"""Thin HTTP adapters to shared job and review use cases."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from ema.api.mock import preview_pdf, snippet_png
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
from ema.api.provisional import PROVISIONAL, example_schema, mock_example, request_body
from ema.audit.sections import Status, get_status, set_status, statuses
from ema.audit.workflow import AuditWorkflow
from ema.core.errors import EmaError
from ema.core.jobs import cancel, create_job, get_job, list_jobs, status, subscribe
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
from ema.core.review.models import Decision, Evidence, Field
from ema.core.workspace import Workspace


class NewJob(BaseModel):
    type: Literal["invoices", "piee", "audit", "reporting"]
    client: str
    year: int | None = None


class SlotInput(BaseModel):
    file_sha: str


class DecisionInput(BaseModel):
    action: Literal["accept", "correct", "reject", "choose"]
    on_revision: int
    value: Any = None
    alternative: str | None = None


class BatchInput(BaseModel):
    fields: list[tuple[str, int]]


class SectionInput(BaseModel):
    status: Literal["done", "n/a", "later", "ready", "missing"]
    on_revision: int
    reason: str | None = None
    confirm: bool = False


class ConfirmInput(BaseModel):
    confirm: bool


class ExportInput(BaseModel):
    final: Literal[True]
    output_id: str | None = None
    readiness_hash: str | None = None
    confirm: bool = False


def install_routes(app: FastAPI, ws: Workspace, *, mock: bool = False) -> None:  # noqa: C901, PLR0915
    def audit_only(job_id: str) -> None:
        if get_job(ws, job_id)["type"] != "audit":
            raise HTTPException(501, "Workflow contract is provisional")

    @app.get("/jobs", tags=["jobs"], response_model=list[Job])
    def jobs() -> list[dict[str, Any]]:
        return list_jobs(ws)

    @app.post("/jobs", tags=["jobs"], response_model=NewJobResult)
    def new_job(body: NewJob) -> dict[str, str]:
        return {"id": create_job(ws, body.type, body.client, body.year)}

    @app.get("/jobs/{job_id}", tags=["jobs"], response_model=Job)
    def job(job_id: str) -> dict[str, object]:
        return get_job(ws, job_id)

    @app.get("/jobs/{job_id}/status", tags=["jobs"], response_model=JobStatus)
    def job_status(job_id: str) -> dict[str, object]:
        return asdict(status(ws, job_id))

    @app.get(
        "/jobs/{job_id}/events",
        tags=["jobs"],
        responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
    )
    def events(job_id: str) -> StreamingResponse:
        get_job(ws, job_id)

        def stream() -> Any:
            for event in subscribe(ws, job_id):
                yield f"data: {json.dumps(asdict(event), ensure_ascii=False)}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/jobs/{job_id}/cancel", tags=["jobs"], response_model=CancelResult)
    def cancel_job(job_id: str) -> dict[str, bool]:
        cancel(ws, job_id)
        return {"cancelled": True}

    @app.delete("/jobs/{job_id}", tags=["jobs"], response_model=DeleteResult)
    def delete_job(job_id: str, body: ConfirmInput) -> dict[str, bool]:
        if not body.confirm:
            raise HTTPException(403, "Human confirmation required")
        ws.delete_job(job_id)
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
        return [asdict(item) for item in ws.list_versions(job_id, slot)]

    @app.put("/jobs/{job_id}/slots/{slot:path}", tags=["documents"], response_model=SlotVersion)
    def put_slot(job_id: str, slot: str, body: SlotInput) -> dict[str, object]:
        return asdict(ws.set_slot(job_id, slot, body.file_sha))

    @app.delete(
        "/jobs/{job_id}/slots/{slot:path}/versions/{version}",
        tags=["documents"],
        response_model=DeleteResult,
    )
    def delete_version(job_id: str, slot: str, version: int) -> dict[str, bool]:
        ws.remove_version(job_id, slot, version)
        return {"deleted": True}

    @app.get("/jobs/{job_id}/fields", tags=["review"], response_model=list[Field])
    def get_fields(
        job_id: str,
        status_filter: Literal[
            "pending", "uncertain", "accepted", "corrected", "rejected", "conflict", "missing"
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
    def change_section(job_id: str, section_id: str, body: SectionInput) -> dict[str, object]:
        audit_only(job_id)
        if body.status in ("done", "n/a") and not body.confirm:
            raise HTTPException(403, "Human confirmation required")
        try:
            return set_status(
                ws,
                job_id,
                section_id,
                Status(body.status),
                "user",
                body.reason,
                on_revision=body.on_revision,
            ).payload()
        except EmaError as exc:
            if exc.code != "stale_revision":
                raise
            raise HTTPException(
                409, {"current_revision": get_status(ws, job_id, section_id).revision}
            ) from exc

    @app.get("/jobs/{job_id}/export/checks", tags=["export"], response_model=ExportChecks)
    def checks(job_id: str) -> dict[str, Any]:
        if mock and get_job(ws, job_id)["type"] != "audit":
            return {
                "readiness": {
                    "draft_ok": True,
                    "final_ok": False,
                    "blocking": [],
                    "warnings": [],
                    "next": [],
                },
                "readiness_hash": "synthetic",
            }
        audit_only(job_id)
        workflow = AuditWorkflow()
        readiness = workflow.readiness(ws, job_id)
        return {
            "readiness": readiness.model_dump(mode="json"),
            "readiness_hash": readiness_hash(ws, job_id, readiness, workflow),
        }

    @app.get(
        "/jobs/{job_id}/outputs/{output_id}",
        tags=["export"],
        responses={
            200: {
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
                }
            }
        },
    )
    def get_output(job_id: str, output_id: str) -> Response:
        if mock:
            get_job(ws, job_id)
            return Response(b"Synthetic output", media_type="application/octet-stream")
        path = output_path(ws, job_id, output_id)
        return FileResponse(path, filename=path.name)

    @app.post("/jobs/{job_id}/export", tags=["export"], response_model=ExportResult)
    def do_export(job_id: str, body: ExportInput, request: Request) -> dict[str, str]:
        if mock and get_job(ws, job_id)["type"] != "audit":
            return {"output_id": "output-exemplu"}
        audit_only(job_id)
        workflow = AuditWorkflow()
        readiness = workflow.readiness(ws, job_id)
        if not readiness.final_ok:
            raise HTTPException(409, "Final export is not ready")
        current_hash = readiness_hash(ws, job_id, readiness, workflow)
        if not body.confirm or body.readiness_hash != current_hash or body.output_id is None:
            raise HTTPException(403, "Revision-bound human approval required")
        if not request.cookies.get("ema_session"):
            raise HTTPException(403, "Human session required")
        approve_final(ws, job_id, body.output_id, current_hash, "user")
        source = output_path(ws, job_id, body.output_id)
        destination = ws.root / "exports" / f"{job_id}-{body.output_id}{source.suffix}"
        destination.parent.mkdir(exist_ok=True)
        export(ws, job_id, workflow, final=True, dest=destination, actor="user")
        return {"output_id": body.output_id}

    def provisional_handler(method: str, route: str) -> Callable[[], Response]:
        def handler() -> Response:
            if mock:
                if route.endswith("preview.pdf"):
                    return Response(preview_pdf(), media_type="application/pdf")
                if route.endswith(".png"):
                    return Response(snippet_png(), media_type="image/png")
                return JSONResponse(mock_example(method, route))
            return JSONResponse({"detail": "Provisional contract"}, status_code=501)

        return handler

    for method, path in PROVISIONAL:
        example = mock_example(method, path)
        body = request_body(method, path)
        content_type = (
            "application/pdf"
            if path.endswith(".pdf")
            else "image/png"
            if path.endswith(".png")
            else "application/json"
        )
        content = (
            {"schema": {"type": "string", "format": "binary"}}
            if content_type != "application/json"
            else {"schema": example_schema(example), "example": example}
        )
        parameters = [
            {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
            for name in re.findall(r"\{(\w+)\}", path)
        ]
        app.add_api_route(
            path,
            provisional_handler(method, path),
            methods=[method],
            tags=["provisional"],
            openapi_extra={
                "x-provisional": True,
                "parameters": parameters,
                **({"requestBody": body} if body is not None else {}),
            },
            responses={
                200: {"content": {content_type: content}},
                501: {"description": "Contract only; use case pending"},
            },
        )
