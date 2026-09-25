"""Invoice batch review adapters."""

from fastapi import FastAPI, Request

from ema.api.models import InvoiceBatchView, InvoiceIdentity, InvoiceIdentityInput
from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.workspace import Workspace
from ema.invoices import identity_review


def _invoice_job(ws: Workspace, job: str) -> None:
    if get_job(ws, job)["type"] != "invoices":
        raise EmaError("wrong_job_type", "Lucrarea nu este un lot de facturi.", "")


def install_invoice_routes(app: FastAPI, ws: Workspace) -> None:
    @app.get("/jobs/{job_id}/invoices", tags=["invoices"], response_model=InvoiceBatchView)
    def invoices(job_id: str) -> dict[str, object]:
        _invoice_job(ws, job_id)
        return identity_review.batch_view(ws, job_id)

    @app.get("/jobs/{job_id}/invoices/identity", tags=["invoices"], response_model=InvoiceIdentity)
    def identity(job_id: str) -> dict[str, object]:
        _invoice_job(ws, job_id)
        return identity_review.identity_view(ws, job_id)

    @app.post("/jobs/{job_id}/invoices/identity", tags=["invoices"], response_model=InvoiceIdentity)
    def confirm(job_id: str, body: InvoiceIdentityInput, request: Request) -> dict[str, object]:
        _invoice_job(ws, job_id)
        if not body.confirm or not getattr(request.state, "human_session", False):
            raise EmaError("human_required", "Confirmarea umană este necesară.", "")
        identity_review.confirm_client(
            ws, job_id, client_id=body.client_id, on_revision=body.on_revision
        )
        return identity_review.identity_view(ws, job_id)
