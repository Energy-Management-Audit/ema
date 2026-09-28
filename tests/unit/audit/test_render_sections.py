"""The draft render marks what it wrote itself `drafted` by Ema; only a human makes it done (D6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from tests.unit.audit.render_seams import run_render, summary_of
from tests.unit.audit.section_marks_seams import (
    base_sha,
    by_id,
    draft,
    journal,
    marked_job,
    publication,
)

from ema.audit import render, render_writers
from ema.audit.catalogue import CATALOGUE
from ema.audit.render_sections import RENDER_DRAFTED
from ema.audit.render_steps import section_ids
from ema.audit.sections import Status, set_status
from ema.audit.workflow import AuditWorkflow
from ema.core.errors import EmaError
from ema.core.review import decide, fields
from ema.core.review.section_transition import SectionState
from ema.core.workspace import Workspace

CONTRACT = [
    *("ch1", "ch1.scop", "ch1.obiective", "ch1.continut", "ch1.intocmire", "ch1.legislatie"),
    *("ch2", "ch3", "ch4", "ch4.productie", "ch4.consum", "ch4.electricitate"),
    *("ch4.electricitate_pv", "ch4.gaz", "ch4.carburant", "ch4.apa", "ch4.echivalent"),
    *("ch4.echiv_electric", "ch4.echiv_pv", "ch4.echiv_gaz", "ch4.echiv_carburant"),
    *("ch4.echiv_total", "ch4.concluzii", "ch4.eficienta", "ch4.specific_electric"),
    *("ch4.specific_pv", "ch4.specific_gaz", "ch4.specific_carburant", "ch4.specific_total"),
    *("ch4.specific_apa", "ch4.intensitate", "ch4.mediu", "ch4.bilant_real", "ch6"),
    *("ch6.indicatori", "ch6.generale", "ch7"),
]
WRITTEN = {"ch3", "ch6", "ch4.concluzii", "ch4.eficienta", "ch4.bilant_real"}


@pytest.fixture
def job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Workspace, str]:
    return marked_job(tmp_path, monkeypatch)


def _present(ws: Workspace, job: str, run: str) -> set[str]:
    with ws.connect() as db:
        folder = ws.artifact_dir(db, job, "audit_render", run)
    return set(section_ids(folder / "Audit-ciorna.docx"))


def test_render_drafted_is_the_contract_list() -> None:
    assert list(RENDER_DRAFTED) == CONTRACT
    assert [section.id for section in CATALOGUE if section.id in RENDER_DRAFTED] == CONTRACT


def test_t1_a_draft_marks_every_present_ready_section_by_ema(
    job: tuple[Workspace, str], tmp_path: Path
) -> None:
    ws, job_id = job
    before = by_id(ws, job_id)
    record = draft(ws, job_id)
    after = by_id(ws, job_id)
    present = _present(ws, job_id, str(record["id"]))
    expected = {
        section_id
        for section_id in RENDER_DRAFTED
        if section_id in present and before[section_id].status == Status.READY
    }
    assert expected >= {"ch1", "ch2", "ch3", "ch4", "ch4.concluzii", "ch6", "ch7"}
    marked = {key for key, state in after.items() if state.status != before[key].status}
    assert marked == expected
    sha = base_sha(tmp_path)
    for section_id in expected:
        state = after[section_id]
        assert (state.status, state.stale) == (Status.DRAFTED, False)
        assert f"base:{sha}" in state.fingerprint
        assert "fact:audit.company_name" in state.fingerprint
        assert (f"fact:narrative.{section_id}" in state.fingerprint) == (section_id in WRITTEN)
        assert journal(ws, job_id, section_id)[-1] == ("ema", "audit_render")
    # Its own marks are what the render read: the draft is current.
    assert publication(ws, str(record["id"])) == "current"


def test_a_change_during_the_draft_still_publishes_stale(
    job: tuple[Workspace, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job_id = job

    def five(*args: object, **_: object) -> None:
        set_status(ws, job_id, "ch7", Status.NA, "user", "altă decizie")
        Path(args[-1]).write_bytes(Path(args[-2]).read_bytes())  # type: ignore[arg-type]

    monkeypatch.setattr(render, "write_five", five)
    record = draft(ws, job_id)
    assert publication(ws, str(record["id"])) == "stale"
    assert by_id(ws, job_id)["ch7"].status == Status.NA


def test_t2_not_marked_when_dropped_failed_or_by_a_final(
    job: tuple[Workspace, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job_id = job
    set_status(ws, job_id, "ch4.bilant_real", Status.NA, "user", "nu se aplică")

    def broken(*_: object, **__: object) -> None:
        raise EmaError("ch4_no_data", "Capitolul 4 nu are date de consum.", "")

    original = render_writers.write_intro

    def intro(source: Path, target: Path, *, section_id: str, text: str | None) -> None:
        if section_id == "ch6":
            raise EmaError("draft_prototype", "Baza nu are un model.", "ch6")
        original(source, target, section_id=section_id, text=text)

    monkeypatch.setattr(render, "write_four", broken)
    monkeypatch.setattr(render, "write_intro", intro)
    record = draft(ws, job_id)
    after = by_id(ws, job_id)
    assert after["ch4.bilant_real"].status == Status.NA
    unmarked = [after[key].status for key in ("ch4", "ch4.concluzii", "ch6")]
    assert unmarked == [Status.READY] * 3  # a failed writer marks nothing
    assert (after["ch3"].status, after["ch7"].status) == (Status.DRAFTED, Status.DRAFTED)
    assert {failure.split(":")[0] for failure in _failures(ws, job_id, str(record["id"]))} == {
        "ch4",
        "ch6",
    }
    before_final = by_id(ws, job_id)
    run_render(ws, job_id, "final")
    assert by_id(ws, job_id) == before_final


def _failures(ws: Workspace, job: str, run: str) -> list[str]:
    return [f"{item.section_id}:{item.code}" for item in summary_of(ws, job, run).failures]


def test_t4_a_corrected_intro_stales_a_done_section_until_the_next_draft(
    job: tuple[Workspace, str],
) -> None:
    ws, job_id = job
    draft(ws, job_id)
    set_status(ws, job_id, "ch3", Status.DONE, "user")
    field = next(item for item in fields(ws, job_id) if item.key == "narrative.ch3")
    decide(ws, job_id, field.id, "correct", field.revision, "user", value="Altă introducere.")
    readiness = AuditWorkflow().readiness(ws, job_id)
    assert "Refaceţi secţiunea: " + _title("ch3") in [
        issue.message for issue in readiness.blocking if issue.code == "stale"
    ]
    stale = by_id(ws, job_id)["ch3"]
    assert (stale.status, stale.stale, stale.changed_input) == (
        Status.DRAFTED,
        True,
        "fact:narrative.ch3",
    )
    draft(ws, job_id)
    again = by_id(ws, job_id)["ch3"]
    assert (again.status, again.stale) == (Status.DRAFTED, False)
    with ws.connect() as db:
        folder = ws.artifact_dir(
            db,
            job_id,
            "audit_render",
            str(db.execute("SELECT id FROM runs ORDER BY ended_at DESC LIMIT 1").fetchone()[0]),
        )
    assert "Altă introducere." in [
        p.text for p in Document(str(folder / "Audit-ciorna.docx")).paragraphs
    ]


def test_t6_an_unconfirmed_render_drafted_section_is_still_open(
    job: tuple[Workspace, str],
) -> None:
    ws, job_id = job
    draft(ws, job_id)
    blocking = AuditWorkflow().readiness(ws, job_id).blocking
    assert f"{_title('ch1')}: Completați și confirmați secțiunea" in [
        issue.message for issue in blocking if issue.code == "section_open"
    ]


def _title(section_id: str) -> str:
    return next(section.title for section in CATALOGUE if section.id == section_id)


def test_t3_done_is_human_only(job: tuple[Workspace, str]) -> None:
    ws, job_id = job
    draft(ws, job_id)
    for actor in ("ema", "agent"):
        with pytest.raises(EmaError) as refused:
            set_status(ws, job_id, "ch1", Status.DONE, actor)  # type: ignore[arg-type]
        assert refused.value.code == "transition_forbidden"
    state: SectionState = by_id(ws, job_id)["ch1"]
    assert state.status == Status.DRAFTED
