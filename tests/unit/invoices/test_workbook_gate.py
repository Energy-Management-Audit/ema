"""Every workbook entry point preserves the batch-client confirmation gate."""

from pathlib import Path

import pytest
from tests.unit.test_invoice_s9b_identity import _job, _row
from tests.workspace_jobs import create_job

from ema.core.errors import EmaError
from ema.core.workspace import Workspace
from ema.invoices import export, start_workbook


@pytest.mark.parametrize("action", [start_workbook, export])
def test_workbook_requires_confirmed_batch_client(tmp_path: Path, action) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws, tmp_path, [_row("invoice.pdf", "ALPHA SRL", "POD0001", "RO123")])

    with pytest.raises(EmaError) as blocked:
        action(ws, job)

    assert blocked.value.code == "invoices_unconfirmed_client"
    assert blocked.value.user_message_ro == "Clientul lotului nu este confirmat."
    with ws.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM outputs WHERE job_id=?", (job,)).fetchone()[0] == 0


@pytest.mark.parametrize("action", [start_workbook, export])
def test_workbook_refuses_changed_invoice_source(tmp_path: Path, action) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(ws, tmp_path, [_row("invoice.pdf", "ALPHA SRL", "POD0001", "RO123")])
    replacement = tmp_path / "replacement.pdf"
    replacement.write_bytes(b"changed synthetic invoice")
    ws.set_slot(job, "invoices/0001", ws.add_file("example", replacement))

    with pytest.raises(EmaError) as blocked:
        action(ws, job)

    assert blocked.value.code == "invoices_stale"


@pytest.mark.parametrize("action", [start_workbook, export])
def test_workbook_requires_invoice_extraction(tmp_path: Path, action) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "invoices", "example", None)

    with pytest.raises(EmaError) as blocked:
        action(ws, job)

    assert blocked.value.code == "invoices_missing"
