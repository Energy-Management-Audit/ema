"""Regression target: an extracted client value remains active after research."""

from datetime import UTC, datetime
from pathlib import Path

from tests.workspace_jobs import create_job

from ema.audit.research_tools import ResearchTools
from ema.audit.research_web import OutboundGuard, Snapshot
from ema.core.review.fields import fields, propose
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace


class NoSearch:
    def search(self, query: str) -> list[dict[str, str]]:
        raise AssertionError(query)


def test_extracted_client_address_survives_online_conflict(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    propose(
        ws,
        job,
        FieldSpec(key="audit.address", label="Address", value_type="text"),
        "Client address",
        [],
        state="extracted",
    )
    tools = ResearchTools(ws, job, "ch2.date_generale", OutboundGuard(ws, job), NoSearch())
    tools.snapshots["sha"] = Snapshot(
        "https://example.org/company",
        "sha",
        datetime.now(UTC),
        "text/plain",
        b"Registered address: Online address",
    )

    tools.record_fact(
        {
            "key": "audit.address",
            "value": "Online address",
            "snapshot_sha": "sha",
            "quote": "Registered address: Online address",
            "trust_reason": "Synthetic public register",
        }
    )

    address = next(field for field in fields(ws, job) if field.key == "audit.address")
    assert address.value == "Client address"
    assert any(candidate.value == "Online address" for candidate in address.alternatives)
