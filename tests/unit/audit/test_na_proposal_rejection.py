"""A human can reject an n/a proposal to the current computed state."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.workspace_jobs import create_job

from ema.api import create_app
from ema.core.errors import EmaError
from ema.core.review.section_transition import SectionState, Status, transition
from ema.core.workspace import Workspace


@pytest.mark.parametrize(
    ("section", "fingerprint", "computed"),
    [
        ("ch2.manager", (), "missing"),
        ("ch1.scop", (), "ready"),
        ("ch1.obiective", ("fact:synthetic",), "drafted"),
    ],
)
def test_se_aplica_uses_outline_computed_status_and_records_journal(
    tmp_path: Path, section: str, fingerprint: tuple[str, ...], computed: str
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    state = SectionState(
        section,
        Status.NA_PROPOSED,
        revision=2,
        reason="Ema proposal",
        fingerprint=fingerprint,
        na_applicable=False,
    )
    with ws.connect() as db:
        db.execute(
            "INSERT INTO section_states(job_id,section_id,revision,data) VALUES (?,?,?,?)",
            (job, section, state.revision, json.dumps(state.payload())),
        )
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"),
        base_url="http://127.0.0.1:8766",
    )
    token = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    headers = {"X-Ema-CSRF": token}
    path = f"/jobs/{job}/sections/{section}"
    outline = client.get(f"/jobs/{job}/audit/outline").json()
    node = next(item for item in outline["nodes"] if item["id"] == section)
    assert node["computed_status"] == computed
    wrong = "ready" if computed != "ready" else "missing"
    stale = client.patch(path, json={"status": wrong, "on_revision": 2}, headers=headers)
    assert stale.status_code == 409
    assert stale.json()["type"] == "urn:ema:error:transition_forbidden"
    accepted = client.patch(path, json={"status": computed, "on_revision": 2}, headers=headers)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == computed
    assert accepted.json()["na_applicable"] is None
    assert accepted.json()["reason"] is None
    decisions = client.get(f"/jobs/{job}/log").json()
    assert decisions[-1]["detail"] == "se aplică"


def test_new_rejection_edge_stays_human_only() -> None:
    proposed = SectionState("ch1.scop", Status.NA_PROPOSED)
    for actor in ("agent", "ema"):
        with pytest.raises(EmaError) as caught:
            transition(proposed, Status.DRAFTED, actor, computed=Status.DRAFTED)
        assert caught.value.code == "transition_forbidden"
