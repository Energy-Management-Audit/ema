"""CLIENT-A1 keyless ANAF acceptance; live network and reference library required."""

from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.audit.cf_owner import company_from_necesar_name, read_owner_cui
from ema.audit.read import read_dossier
from ema.audit.research_tools import ANAF_URL, ResearchTools
from ema.audit.research_web import OutboundGuard
from ema.core.review.fields import propose
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace

pytestmark = [pytest.mark.golden, pytest.mark.network]


class NoSearch:
    def search(self, query: str) -> list[dict[str, str]]:
        raise AssertionError(f"No live search backend configured: {query}")


def test_CLIENT-A1_anaf_with_snapshot(reference_library: Path, tmp_path: Path) -> None:
    received = reference_library / "audit/cases/audit-case-a/received"
    necesar = next(received.glob("*Necesar info*.xls"))
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "CLIENT-A1", 2026)
    read_dossier(ws, job, necesar)
    located = read_owner_cui(
        list(received.glob("*Extras_Informare_CF*.pdf")), company_from_necesar_name(necesar)
    )
    assert ws.add_file("CLIENT-A1", located.source) == located.evidence.file_sha
    propose(
        ws,
        job,
        FieldSpec(key="audit.cui", label="CUI", value_type="text"),
        located.cui,
        [located.evidence],
        state="extracted",
    )
    tools = ResearchTools(ws, job, "ch2.date_generale", OutboundGuard(ws, job), NoSearch())
    result = tools.registry_lookup({"cui": located.cui})
    assert result["url"] == ANAF_URL
    assert result["caen"] and result["address"]
    for key, value in (("audit.caen_code", result["caen"]), ("audit.address", result["address"])):
        record = tools.record_fact(
            {
                "key": key,
                "value": value,
                "snapshot_sha": result["snapshot_sha"],
                "quote": value,
                "trust_reason": "Official ANAF taxpayer register",
            }
        )
        assert record["evidence"]
    if result["registration"]:
        tools.record_fact(
            {
                "key": "audit.registrul_comertului",
                "value": result["registration"],
                "snapshot_sha": result["snapshot_sha"],
                "quote": result["registration"],
                "trust_reason": "Official ANAF taxpayer register",
            }
        )
    else:
        missing = tools.mark_registry_missing({"snapshot_sha": result["snapshot_sha"]})
        assert missing["reason"] == "missing: not in registry response"
    assert result["locality"], "ANAF did not return a registered locality"
    map_result = tools.map_locality(
        {"locality": result["locality"], "county": result["county"] or ""}
    )
    print(f"S13 map status: {map_result['status']}; reason: {map_result.get('reason', 'none')}")
    assert map_result["status"] == "rendered" or (
        map_result["status"] == "later: map" and map_result["reason"]
    )
