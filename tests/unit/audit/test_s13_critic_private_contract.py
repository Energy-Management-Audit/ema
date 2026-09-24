"""Regression target: formatted private contract IDs must stay local."""

from pathlib import Path

import pytest

from ema.audit.research_web import OutboundGuard
from ema.core.errors import EmaError
from ema.core.jobs import create_job
from ema.core.review.fields import propose
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("query", "AB 12345"),
        ("url", "https://example.org/AB.12345"),
        ("url", "https://example.org/search?q=AB%2D12345"),
        ("url", "https://example.org/AB%252012345"),
    ],
)
def test_private_contract_with_changed_separator_is_refused(
    tmp_path: Path, kind: str, value: str
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    guard = OutboundGuard(ws, job, ("Contract nr: AB-12345",))

    with pytest.raises(EmaError) as error:
        guard.check(kind, value)
    assert error.value.code == "outbound_refused"


def test_numeric_identifier_with_separators_is_refused(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    propose(
        ws,
        job,
        FieldSpec(key="audit.contract_number", label="Contract", value_type="text"),
        "12345",
        [],
        state="extracted",
    )
    guard = OutboundGuard(ws, job)
    with pytest.raises(EmaError) as error:
        guard.check("url", "https://example.org/find/12-345")
    assert error.value.code == "outbound_refused"
