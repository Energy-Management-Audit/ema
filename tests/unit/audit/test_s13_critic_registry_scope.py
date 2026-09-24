"""Regression target: ANAF lookup is bound to the verified owner CUI."""

from pathlib import Path
from typing import Any

import pytest

from ema.audit import research_tools
from ema.audit.research_tools import ResearchTools
from ema.audit.research_web import OutboundGuard
from ema.core.errors import EmaError
from ema.core.jobs import create_job
from ema.core.review.fields import propose
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace


class NoSearch:
    def search(self, query: str) -> list[dict[str, str]]:
        raise AssertionError(query)


def test_registry_lookup_rejects_cui_other_than_job_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    propose(
        ws,
        job,
        FieldSpec(key="audit.cui", label="CUI", value_type="text"),
        "12345678",
        [],
        state="extracted",
    )
    tools = ResearchTools(ws, job, "ch2.date_generale", OutboundGuard(ws, job), NoSearch())
    calls: list[str] = []

    def reject_network(*args: Any, **kwargs: Any) -> Any:
        calls.append("network")
        raise AssertionError("An unrelated CUI reached the network")

    monkeypatch.setattr(research_tools, "fetch", reject_network)
    with pytest.raises(EmaError) as error:
        tools.registry_lookup({"cui": "87654321"})
    assert error.value.code == "registry_mismatch"
    assert not calls
