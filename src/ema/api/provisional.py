"""The live per-section draft operation remains provisional."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from ema.api.errors import problem
from ema.core.workspace import Workspace

PROVISIONAL = [
    ("POST", "/jobs/{job_id}/sections/{section_id}/draft"),
]

REASONS = {
    "/jobs/{job_id}/sections/{section_id}/draft": "live per-section draft agent pending",
}

_EXAMPLES: dict[str, dict[str, Any]] = {
    "/jobs/{job_id}/sections/{section_id}/draft": {
        "run_id": "run-exemplu",
        "stage": "draft",
        "state": "running",
    },
}

_REQUESTS: dict[str, dict[str, Any]] = {
    "/jobs/{job_id}/sections/{section_id}/draft": {"on_revision": 1},
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
                return JSONResponse(_EXAMPLES[route])
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
