"""Download the blank, versioned measures input form."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse

from ema.audit.measures_form import write_measures_form
from ema.core.workspace import Workspace


def install_audit_forms(app: FastAPI, ws: Workspace) -> None:
    @app.get(
        "/audit/forms/masuri-propuse.xlsx",
        tags=["audit"],
        response_class=FileResponse,
        responses={
            200: {
                "content": {
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                }
            }
        },
    )
    def measures_form() -> FileResponse:
        destination = ws.root / "forms" / "Masuri propuse.xlsx"
        if not destination.exists():
            write_measures_form(destination)
        return FileResponse(
            destination,
            filename="Masuri propuse.xlsx",
            headers={"Content-Disposition": 'attachment; filename="Masuri propuse.xlsx"'},
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
