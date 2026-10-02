"""The auditor's answer for a carrier her dossier lists without a reading."""

from ema.audit.workflow import AuditWorkflow
from ema.core.review import decide, fields
from ema.core.workspace import Workspace


def confirm_missing_gpl(ws: Workspace, job: str) -> None:
    """Her GPL has no reading: the final lists it per year until she confirms it missing."""
    blocking = [issue for issue in AuditWorkflow().readiness(ws, job).blocking]
    gaps = [issue for issue in blocking if issue.code == "carrier_incomplete"]
    assert sorted(issue.message for issue in gaps) == [
        f"Lipseşte consumul de GPL pentru {year}." for year in (2023, 2024, 2025)
    ]
    for issue in gaps:
        field = next(item for item in fields(ws, job) if item.id == issue.field_id)
        decide(ws, job, field.id, "accept", field.revision, "user")
