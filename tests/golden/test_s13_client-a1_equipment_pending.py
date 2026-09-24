"""CLIENT-A1 live-equipment acceptance harness, pending a controlled search API."""

from pathlib import Path

import pytest

from ema.audit.read import read_dossier
from ema.core.jobs import create_job
from ema.core.review.fields import fields
from ema.core.workspace import Workspace

pytestmark = [pytest.mark.golden, pytest.mark.network, pytest.mark.live_research]


def test_CLIENT-A1_ten_sourced_equipment_models(reference_library: Path, tmp_path: Path) -> None:
    received = reference_library / "audit/cases/audit-case-a/received"
    necesar = next(received.glob("*Necesar info*.xls"))
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "CLIENT-A1", 2026)
    read_dossier(ws, job, necesar)
    models = [
        field
        for field in fields(ws, job)
        if field.key.startswith("audit.equipment.")
        and field.key.endswith(".denumire")
        and isinstance(field.value, str)
        and field.value.strip()
    ]
    assert len(models) >= 10, "CLIENT-A1 dossier does not provide ten equipment names"
    pytest.fail("pending live search backend: cannot verify ten sourced CLIENT-A1 equipment entries")
