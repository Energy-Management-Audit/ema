"""Select the workflow shared by export and overview."""

from ema.audit.workflow import AuditWorkflow
from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.workspace import Workspace
from ema.invoices import InvoiceWorkflow
from ema.piee.review_workflow import PieeWorkflow


def workflow_for(ws: Workspace, job_id: str) -> AuditWorkflow | PieeWorkflow | InvoiceWorkflow:
    job_type = get_job(ws, job_id)["type"]
    if job_type == "audit":
        return AuditWorkflow()
    if job_type == "piee":
        return PieeWorkflow()
    if job_type == "invoices":
        return InvoiceWorkflow()
    raise EmaError("wrong_job_type", "Exportul nu este disponibil.", "")
