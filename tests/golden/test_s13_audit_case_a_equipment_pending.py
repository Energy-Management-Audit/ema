"""audit_case_a live equipment search through Brave; every query passes OutboundGuard.

Opt-in: EMA_LIVE_RESEARCH_GOLDEN=1 plus a Brave key (EMA_BRAVE_API_KEY or the keyring).
"""

import os
from pathlib import Path

import pytest
from keyring.backends import macOS
from pydantic import SecretStr
from tests.golden.cases import case_path
from tests.workspace_jobs import create_job

from ema.audit.read import read_dossier
from ema.audit.research_tools import ResearchTools
from ema.audit.research_web import OutboundGuard
from ema.audit.search_brave import BraveSearch
from ema.core.config import Settings
from ema.core.errors import EmaError
from ema.core.review.fields import fields
from ema.core.workspace import Workspace

pytestmark = [pytest.mark.golden, pytest.mark.network, pytest.mark.live_research]


def test_audit_case_a_ten_sourced_equipment_models(reference_library: Path, tmp_path: Path) -> None:
    if os.environ.get("EMA_LIVE_RESEARCH_GOLDEN") != "1":
        pytest.skip("live search is opt-in: set EMA_LIVE_RESEARCH_GOLDEN=1")
    # The suite-wide fixture blanks the real keyring, so the golden asks the macOS backend itself.
    key = Settings().brave_key() or (
        SecretStr(stored)
        if (stored := macOS.Keyring().get_password("Ema", "brave_api_key"))
        else None
    )
    assert key is not None, "no Brave key in EMA_BRAVE_API_KEY or the keyring"
    received = reference_library / case_path("audit-case-a", "received")
    necesar = next(received.glob("*Necesar info*.xls"))
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "audit-case-a", 2026)
    read_dossier(ws, job, necesar)
    models = sorted(
        {
            field.value.strip()
            for field in fields(ws, job)
            if field.key.startswith("audit.equipment.")
            and field.key.endswith(".denumire")
            and isinstance(field.value, str)
            and field.value.strip()
        }
    )
    assert len(models) >= 10, "audit_case_a dossier does not provide ten equipment names"
    tools = ResearchTools(ws, job, "ch3.equipment", OutboundGuard(ws, job), BraveSearch(key))
    # The guard treats a full dossier equipment name as a private value and refuses it, as
    # designed; the query is the leading words only. Refusals are counted, never bypassed.
    sourced = refused = 0  # refused is reported in the failure message
    for model in models:
        if sourced == 10:
            break
        query = " ".join(model.split()[:2]) + " fisa tehnica"
        try:
            results = tools.search({"query": query})
        except EmaError as exc:
            assert exc.code == "outbound_refused"
            refused += 1
            continue
        assert isinstance(results, list)
        if any(row["url"].startswith("https://") and row["snippet"] for row in results):
            sourced += 1
    assert sourced == 10, f"{sourced} sourced, guard refused {refused} queries"
