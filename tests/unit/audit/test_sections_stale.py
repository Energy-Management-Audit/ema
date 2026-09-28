"""The chapter confirmation: one human PATCH, refused whole when a confirmed draft is stale (D7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.unit.audit.section_marks_seams import BASE, by_id, draft, journal, marked_job, session

from ema.api import create_app
from ema.audit.sections_bulk import patch_sections
from ema.core.errors import EmaError
from ema.core.review import decide, fields
from ema.core.workspace import Workspace


@pytest.fixture
def drafted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Workspace, str]:
    ws, job = marked_job(tmp_path, monkeypatch)
    draft(ws, job)
    return ws, job


def _items(
    ws: Workspace, job: str, *section_ids: str, confirm: bool = True
) -> list[dict[str, object]]:
    states = by_id(ws, job)
    return [
        {
            "section_id": section_id,
            "status": "done",
            "on_revision": states[section_id].revision,
            "confirm": confirm,
        }
        for section_id in section_ids
    ]


def _decisions(ws: Workspace, job: str) -> list[dict[str, object]]:
    with ws.connect() as db:
        rows = db.execute("SELECT data FROM decisions WHERE job_id=? ORDER BY seq", (job,))
        return [json.loads(row["data"]) for row in rows]


def test_t3_the_bulk_confirmation_is_a_human_act(drafted: tuple[Workspace, str]) -> None:
    ws, job = drafted
    client, headers = session(ws)
    unconfirmed = client.patch(
        f"/jobs/{job}/sections", json=_items(ws, job, "ch1", confirm=False), headers=headers
    )
    assert (unconfirmed.status_code, unconfirmed.json()["type"]) == (
        403,
        "urn:ema:error:human_required",
    )
    anonymous = TestClient(create_app(ws, 8766, launch_code="other"), base_url=BASE)
    refused = anonymous.patch(f"/jobs/{job}/sections", json=_items(ws, job, "ch1", "ch7"))
    assert refused.status_code == 403
    before = len(_decisions(ws, job))
    confirmed = client.patch(
        f"/jobs/{job}/sections", json=_items(ws, job, "ch1", "ch7"), headers=headers
    )
    assert confirmed.status_code == 200, confirmed.json()
    assert [item["status"] for item in confirmed.json()] == ["done", "done"]
    new = _decisions(ws, job)[before:]
    assert [(item["field_id"], item["actor"]) for item in new] == [("ch1", "user"), ("ch7", "user")]


def test_t10_a_text_corrected_just_before_the_click_refuses_the_whole_batch(
    drafted: tuple[Workspace, str],
) -> None:
    ws, job = drafted
    assert "fact:narrative.ch3" in by_id(ws, job)["ch3"].fingerprint
    items = _items(ws, job, "ch3", "ch7")
    ch7_revision = by_id(ws, job)["ch7"].revision
    field = next(item for item in fields(ws, job) if item.key == "narrative.ch3")
    decide(ws, job, field.id, "correct", field.revision, "user", value="Altă introducere.")
    client, headers = session(ws)
    refused = client.patch(f"/jobs/{job}/sections", json=items, headers=headers)
    assert refused.status_code == 409
    assert refused.json() == {
        "type": "urn:ema:error:sections_stale",
        "title": "Unele secţiuni au ciorna veche.",
        "status": 409,
    }
    with pytest.raises(EmaError) as again:
        patch_sections(ws, job, items)
    assert (again.value.code, again.value.detail) == ("sections_stale", "ch3")
    states = by_id(ws, job)
    assert (states["ch3"].status.value, states["ch7"].status.value) == ("drafted", "drafted")
    assert (states["ch3"].stale, states["ch3"].changed_input) == (True, "fact:narrative.ch3")
    assert journal(ws, job, "ch3")[-1] == ("ema", "fact:narrative.ch3")
    assert states["ch7"].revision == ch7_revision


def test_t11_a_base_switched_just_before_the_click_refuses_the_whole_batch(
    drafted: tuple[Workspace, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = drafted
    items = _items(ws, job, "ch3", "ch7")
    renewed = tmp_path / "base-renewed.docx"
    renewed.write_bytes((tmp_path / "base.docx").read_bytes() + b" renewed")
    monkeypatch.setenv("EMA_AUDIT_BASE_DOCUMENT", str(renewed))
    with pytest.raises(EmaError) as refused:
        patch_sections(ws, job, items)
    assert (refused.value.code, refused.value.detail) == ("sections_stale", "ch3,ch7")
    states = by_id(ws, job)
    assert all(
        states[key].stale and states[key].status.value == "drafted" for key in ("ch3", "ch7")
    )


def test_t12_every_stale_id_is_named_in_catalogue_order(
    drafted: tuple[Workspace, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = drafted
    items = _items(ws, job, "ch7", "ch3", "ch1")
    renewed = tmp_path / "base-renewed.docx"
    renewed.write_bytes(b"renewed base")
    monkeypatch.setenv("EMA_AUDIT_BASE_DOCUMENT", str(renewed))
    with pytest.raises(EmaError) as refused:
        patch_sections(ws, job, items)
    assert refused.value.detail == "ch1,ch3,ch7"
