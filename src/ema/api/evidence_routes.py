"""PDF evidence image HTTP adapters."""

from typing import Any, Literal

from fastapi import FastAPI, Query, Response

from ema.core.pdf import render_evidence_png
from ema.core.workspace import Workspace

_PNG_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}
}


def install_evidence_routes(app: FastAPI, ws: Workspace, *, mock: bool = False) -> None:
    @app.get(
        "/evidence/{evidence_id}/snippet.png",
        tags=["review"],
        response_class=Response,
        responses=_PNG_RESPONSE,
    )
    def snippet(evidence_id: str, highlight: Literal["0", "1"] = Query("0")) -> Response:
        payload = render_evidence_png(ws, evidence_id, mode="snippet", highlight=highlight == "1")
        return Response(
            payload, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"}
        )

    @app.get(
        "/evidence/{evidence_id}/page.png",
        tags=["review"],
        response_class=Response,
        responses=_PNG_RESPONSE,
    )
    def page(evidence_id: str) -> Response:
        payload = render_evidence_png(ws, evidence_id, mode="page")
        return Response(
            payload, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"}
        )
