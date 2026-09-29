"""Invoice batch review adapters."""

import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse

from ema.api.invoice_models import (
    InvoiceBatchView,
    InvoiceIdentity,
    InvoiceIdentityInput,
    InvoiceUpload,
)
from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.pdf import render_invoice_crop_png, render_page_png
from ema.core.workspace import Workspace
from ema.core.workspace.conversion import active_version
from ema.invoices import identity_review, identity_view
from ema.invoices.batch_view import batch_view
from ema.invoices.uploads import add_invoice_files


def _invoice_job(ws: Workspace, job: str) -> None:
    if get_job(ws, job)["type"] != "invoices":
        raise EmaError("wrong_job_type", "Lucrarea nu este un lot de facturi.", "")


def _invoice_path(ws: Workspace, job: str, slot: str) -> Path:
    _invoice_job(ws, job)
    if re.fullmatch(r"invoices/[0-9]{4}", slot) is None:
        raise EmaError("invalid_slot", "Numele fişierului este invalid.", "")
    version = active_version(ws, job, slot)
    if version is None:
        raise EmaError("file_missing", "Fişierul nu există.", "")
    client = str(get_job(ws, job)["client_slug"])
    path = ws.file_path(client, version.file_sha)
    if not path.is_file():
        raise EmaError("file_missing", "Fişierul nu există.", "")
    if path.suffix.lower() != ".pdf":
        raise EmaError("file_type", "Fişierul nu este PDF.", "")
    return path


def install_invoice_routes(app: FastAPI, ws: Workspace) -> None:
    @app.post("/jobs/{job_id}/invoices/files", tags=["invoices"], response_model=InvoiceUpload)
    def upload(
        job_id: str,
        files: Annotated[list[UploadFile], File()],
        replace: str | None = Query(None),
    ) -> dict[str, list[dict[str, str]]]:
        return add_invoice_files(
            ws, job_id, [(item.filename or "", item.file) for item in files], replace
        )

    @app.get("/jobs/{job_id}/invoices/page.png", tags=["invoices"], response_class=Response)
    def page(
        job_id: str, slot: str, page: int, crop: Literal["active_energy"] | None = Query(None)
    ) -> Response:
        path = _invoice_path(ws, job_id, slot)
        content: bytes | None = None
        if crop == "active_energy":
            source = next(
                (
                    row
                    for row in batch_view(ws, job_id)["rows"]
                    if row["slot"] == slot
                    and row["sources"].get("active_energy", {}).get("page") == page
                    and row["consumption_kwh"] is not None
                ),
                None,
            )
            if source is not None:
                content = render_invoice_crop_png(
                    path,
                    page,
                    str(source["consumption_kwh"]),
                    str(source["sources"]["active_energy"]["snippet"]),
                )
        return Response(
            content if content is not None else render_page_png(path, page),
            media_type="image/png",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/jobs/{job_id}/invoices/file", tags=["invoices"], response_class=FileResponse)
    def file(job_id: str, slot: str) -> FileResponse:
        return FileResponse(
            _invoice_path(ws, job_id, slot),
            media_type="application/pdf",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/jobs/{job_id}/invoices", tags=["invoices"], response_model=InvoiceBatchView)
    def invoices(job_id: str) -> dict[str, object]:
        _invoice_job(ws, job_id)
        return batch_view(ws, job_id)

    @app.get("/jobs/{job_id}/invoices/identity", tags=["invoices"], response_model=InvoiceIdentity)
    def identity(job_id: str) -> dict[str, object]:
        _invoice_job(ws, job_id)
        return identity_view.identity_view(ws, job_id)

    @app.post("/jobs/{job_id}/invoices/identity", tags=["invoices"], response_model=InvoiceIdentity)
    def confirm(job_id: str, body: InvoiceIdentityInput, request: Request) -> dict[str, object]:
        _invoice_job(ws, job_id)
        if not body.confirm or not getattr(request.state, "human_session", False):
            raise EmaError("human_required", "Confirmarea umană este necesară.", "")
        identity_review.confirm_client(
            ws, job_id, client_id=body.client_id, on_revision=body.on_revision
        )
        return identity_view.identity_view(ws, job_id)
