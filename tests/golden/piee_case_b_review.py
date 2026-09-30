"""Review the filed case-b exceptions through the public field decision route."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ema.api import create_app
from ema.core.review import fields, log
from ema.core.review.evidence import get_evidence
from ema.core.review.models import Cell, Field
from ema.core.workspace import Workspace
from ema.piee.review_workflow import PieeWorkflow

FILED_REASON = "filed total kept, components differ"
MISSING_KEY = "carrier.electricity_pv.2024"
FILED_KEYS = (
    "annual.total_tep",
    "tep.carrier.electricity_pv.2025",
    "tep.internal_total.2025",
)


def _field(ws: Workspace, job: str, key: str) -> Field:
    return next(item for item in fields(ws, job) if item.key == key)


def _source_refs(ws: Workspace, evidence_ids: list[str]) -> set[str]:
    refs: set[str] = set()
    for evidence_id in evidence_ids:
        locator = get_evidence(ws, evidence_id).locator
        if isinstance(locator, Cell):
            refs.add(locator.ref)
    return refs


def review_case_b_reconciliation(ws: Workspace, job: str) -> None:
    """Confirm the missing PV reading and choose filed values with both cells retained."""
    readiness = PieeWorkflow().readiness(ws, job)
    by_id = {item.id: item for item in fields(ws, job)}
    assert not readiness.final_ok
    assert {
        by_id[issue.field_id].key
        for issue in readiness.blocking
        if issue.code == "carrier_incomplete" and issue.field_id is not None
    } == {MISSING_KEY}
    assert {
        by_id[issue.field_id].key
        for issue in readiness.blocking
        if issue.code == "conflict"
        and issue.field_id is not None
        and by_id[issue.field_id].key.startswith(("annual.", "anexa.", "tep.", "co2."))
    } == set(FILED_KEYS)
    missing = _field(ws, job, MISSING_KEY)
    assert missing.value is None and missing.presence == "not_found" and missing.required

    client = TestClient(create_app(ws, 8766, launch_code="code"), base_url="http://127.0.0.1:8766")
    csrf = client.post("/session", json={"code": "code"}).json()["csrf"]
    headers = {"x-ema-csrf": csrf}

    accepted = client.post(
        f"/jobs/{job}/fields/{missing.id}/decide",
        json={"action": "accept", "on_revision": missing.revision},
        headers=headers,
    )
    assert accepted.status_code == 200
    assert accepted.json()["after"]["presence"] == "not_found"
    assert accepted.json()["after"]["review"] == "accepted"

    for key in FILED_KEYS:
        field = _field(ws, job, key)
        filed = [
            candidate
            for candidate in field.alternatives
            if any(
                ref.startswith("Date anuale!" if key == "annual.total_tep" else "TEP!")
                for ref in _source_refs(ws, candidate.evidence)
            )
        ]
        assert len(filed) == 1, key
        original_refs = {
            ref for candidate in field.alternatives for ref in _source_refs(ws, candidate.evidence)
        }
        assert len(original_refs) >= 2, key
        response = client.post(
            f"/jobs/{job}/fields/{field.id}/decide",
            json={
                "action": "choose",
                "on_revision": field.revision,
                "alternative": filed[0].id,
                "reason": FILED_REASON,
            },
            headers=headers,
        )
        assert response.status_code == 200, (key, response.text)
        assert response.json()["detail"] == FILED_REASON
        reviewed = _field(ws, job, key)
        assert reviewed.chosen == filed[0].id
        assert {
            ref
            for candidate in reviewed.alternatives
            for ref in _source_refs(ws, candidate.evidence)
        } == original_refs

    blocking = PieeWorkflow().readiness(ws, job).blocking
    assert {decision.field_id for decision in log(ws, job) if decision.detail == FILED_REASON} == {
        _field(ws, job, key).id for key in FILED_KEYS
    }
    assert not any(issue.code == "carrier_incomplete" for issue in blocking)
    assert not any(
        issue.code == "conflict"
        and issue.field_id is not None
        and by_id[issue.field_id].key in FILED_KEYS
        for issue in blocking
    )
