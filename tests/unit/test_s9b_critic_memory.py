"""Regression cases for batch client identity memory."""

from __future__ import annotations

from pathlib import Path

from test_invoice_s9b_identity import _job, _row

from ema.clients import find_by_pod
from ema.core.workspace import Workspace
from ema.invoices.identity_review import confirm_client, resolved_outcomes


def test_contradicting_invoice_pod_is_not_remembered_as_confirmed_client(
    tmp_path: Path,
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = _job(
        ws,
        tmp_path,
        [
            _row("alpha-1.pdf", "ALPHA SRL", "POD-ALPHA", "RO123"),
            _row("alpha-2.pdf", "ALPHA SRL", "POD-ALPHA", "RO123"),
            _row("beta.pdf", "BETA SA", "POD-BETA", "RO456"),
        ],
    )

    confirm_client(ws, job)
    assert resolved_outcomes(ws, job)[2]["status"] == "requires_review"
    assert find_by_pod(ws, "POD-BETA") == []
