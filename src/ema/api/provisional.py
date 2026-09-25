"""Five deliberately provisional operations and schema-valid synthetic examples."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from ema.api.errors import problem
from ema.api.mock import preview_pdf
from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.jobs.outputs import get_output as stored_output
from ema.core.workspace import Workspace

PROVISIONAL = [
    ("POST", "/jobs/{job_id}/sections/{section_id}/draft"),
    ("PATCH", "/jobs/{job_id}/deadline"),
    ("GET", "/jobs/{job_id}/preview.pdf"),
    ("GET", "/jobs/{job_id}/package"),
    ("POST", "/jobs/{job_id}/invoices/{invoice_id}/anomaly"),
]

REASONS = {
    "/jobs/{job_id}/sections/{section_id}/draft": "live per-section draft agent pending",
    "/jobs/{job_id}/deadline": "deadline business rule pending",
    "/jobs/{job_id}/preview.pdf": "audit general render pending (/preview.pdf)",
    "/jobs/{job_id}/package": "package 7a assembly pending",
    "/jobs/{job_id}/invoices/{invoice_id}/anomaly": "invoice anomaly business rule pending",
}

_EXAMPLES: dict[str, dict[str, Any]] = {
    "/jobs/{job_id}/sections/{section_id}/draft": {
        "run_id": "run-exemplu",
        "stage": "draft",
        "state": "running",
    },
    "/jobs/{job_id}/deadline": {"deadline": "2026-12-31", "revision": 2},
    "/jobs/{job_id}/package": {
        "files": [{"id": "output-exemplu", "name": "exemplu.docx", "size_bytes": 4096}],
        "checks": [{"code": "sources", "ok": True, "detail": "Surse verificate"}],
    },
    "/jobs/{job_id}/invoices/{invoice_id}/anomaly": {
        "invoice_id": "invoice-exemplu",
        "resolution": "keep_in_month",
        "decision_id": "decision-exemplu",
    },
}

_REQUESTS: dict[str, dict[str, Any]] = {
    "/jobs/{job_id}/sections/{section_id}/draft": {"on_revision": 1},
    "/jobs/{job_id}/deadline": {"deadline": "2026-12-31", "on_revision": 1},
    "/jobs/{job_id}/invoices/{invoice_id}/anomaly": {
        "resolution": "keep_in_month",
        "on_revision": 1,
    },
}


def example_schema(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        mapping = cast("dict[str, Any]", value)
        return {
            "type": "object",
            "properties": {key: example_schema(item) for key, item in mapping.items()},
            "required": list(mapping),
        }
    if isinstance(value, list):
        items = cast("list[Any]", value)
        return {"type": "array", "items": example_schema(items[0]) if items else {}}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    return {"type": "string"}


def install_provisional_routes(app: FastAPI, ws: Workspace, *, mock: bool = False) -> None:
    def provisional_handler(route: str) -> Callable[[Request], Response]:
        def handler(request: Request) -> Response:
            if mock:
                if route.endswith("preview.pdf"):
                    return Response(
                        preview_pdf(),
                        media_type="application/pdf",
                        headers={"X-Content-Type-Options": "nosniff"},
                    )
                return JSONResponse(_EXAMPLES[route])
            if route.endswith("preview.pdf"):
                job_id = str(request.path_params["job_id"])
                job_type = get_job(ws, job_id)["type"]
                if job_type == "piee":
                    with ws.connect() as db:
                        row = db.execute(
                            "SELECT id FROM outputs WHERE job_id=? AND relative_path LIKE '%.pdf' "
                            "ORDER BY seq DESC LIMIT 1",
                            (job_id,),
                        ).fetchone()
                    if row is None:
                        raise EmaError("output_missing", "Previzualizarea lipsește.", "")
                    metadata, relative = stored_output(ws, job_id, str(row["id"]))
                    return FileResponse(
                        ws.path(relative),
                        filename=str(metadata["download_name"]),
                        media_type="application/pdf",
                        headers={"X-Content-Type-Options": "nosniff"},
                    )
                if job_type != "audit":
                    raise EmaError("wrong_job_type", "Lucrarea este invalidă.", "")
            return problem("provisional_contract", 501)

        return handler

    for method, path in PROVISIONAL:
        request = _REQUESTS.get(path)
        body = (
            {
                "required": True,
                "content": {
                    "application/json": {"schema": example_schema(request), "example": request}
                },
            }
            if request is not None
            else None
        )
        content_type = "application/pdf" if path.endswith(".pdf") else "application/json"
        content = (
            {"schema": {"type": "string", "format": "binary"}}
            if content_type == "application/pdf"
            else {"schema": example_schema(_EXAMPLES[path]), "example": _EXAMPLES[path]}
        )
        app.add_api_route(
            path,
            provisional_handler(path),
            methods=[method],
            tags=["provisional"],
            response_class=Response,
            openapi_extra={
                "x-provisional": REASONS[path],
                "parameters": [
                    {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
                    for name in re.findall(r"\{(\w+)\}", path)
                ],
                **({"requestBody": body} if body is not None else {}),
            },
            responses={200: {"content": {content_type: content}}},
        )
