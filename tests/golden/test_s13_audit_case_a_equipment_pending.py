"""audit_case_a live-equipment acceptance harness, pending a controlled search API."""

from pathlib import Path

import pytest
from tests.golden.cases import case_path
from tests.workspace_jobs import create_job

from ema.audit.read import read_dossier
from ema.core.review.fields import fields
from ema.core.workspace import Workspace

pytestmark = [pytest.mark.golden, pytest.mark.network, pytest.mark.live_research]


def test_audit_case_a_ten_sourced_equipment_models(reference_library: Path, tmp_path: Path) -> None:
    received = reference_library / case_path("audit-case-a", "received")
    necesar = next(received.glob("*Necesar info*.xls"))
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "audit-case-a", 2026)
    read_dossier(ws, job, necesar)
    models = [
        field
        for field in fields(ws, job)
        if field.key.startswith("audit.equipment.")
        and field.key.endswith(".denumire")
        and isinstance(field.value, str)
        and field.value.strip()
    ]
    assert len(models) >= 10, "audit_case_a dossier does not provide ten equipment names"
    pytest.fail(
        "pending live search backend: cannot verify ten sourced audit_case_a equipment entries"
    )
