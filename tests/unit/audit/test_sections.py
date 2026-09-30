"""The §5.9 status table and section decisions use the shared Jurnal."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from tests.workspace_jobs import create_job
from typer.testing import CliRunner

from ema.audit.applicability import applies
from ema.audit.catalogue import CATALOGUE, AuditFact, Condition, MaterialKind
from ema.audit.sections import (
    SectionState,
    Status,
    _save,
    audit_readiness,
    get_status,
    mark_drafted,
    recompute_ready,
    record_material,
    set_status,
    transition,
)
from ema.audit.workflow import AuditWorkflow
from ema.cli import _app
from ema.cli import review as cli_review
from ema.core.errors import EmaError
from ema.core.review import decide, export, log, propose, undo
from ema.core.review.models import Field
from ema.core.workspace import Workspace
from ema.energy_data.carriers import Carrier
from ema.energy_data.model import field_key


def mark_stale(ws: Workspace, job: str, section_id: str, changed_input: str) -> SectionState:
    before = get_status(ws, job, section_id)
    if changed_input not in before.fingerprint:
        return before
    after = transition(before, Status.DRAFTED, "ema", changed_input)
    return _save(ws, job, before, after, "ema", changed_input)


def _job(tmp_path: Path) -> tuple[Workspace, str]:
    ws = Workspace(tmp_path / "workspace")
    return ws, create_job(ws, "audit", "synthetic", 2026)


def _code(action, code: str = "transition_forbidden") -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(EmaError) as caught:
        action()
    assert caught.value.code == code


def test_transition_table_and_actor_guards() -> None:
    missing = SectionState("ch1")
    ready = transition(missing, Status.READY, "ema")
    assert transition(ready, Status.MISSING, "ema").status == Status.MISSING
    drafted = transition(ready, Status.DRAFTED, "agent")
    done = transition(drafted, Status.DONE, "user")
    assert done.status == Status.DONE
    stale = transition(
        SectionState("ch1", Status.DONE, fingerprint=("fact:x",)), Status.DRAFTED, "ema", "fact:x"
    )
    assert stale.stale and stale.changed_input == "fact:x"
    assert not transition(stale, Status.DRAFTED, "agent").stale
    later = transition(done, Status.LATER, "user", "await visit")
    assert (
        transition(
            later, Status.MISSING, "ema", awaited_arrived=True, computed=Status.MISSING
        ).status
        == Status.MISSING
    )
    assert (
        transition(later, Status.MISSING, "user", computed=Status.MISSING).status == Status.MISSING
    )
    na = transition(done, Status.NA, "user")
    assert transition(na, Status.DRAFTED, "user", computed=Status.DRAFTED).status == Status.DRAFTED
    for state, target, actor in (
        (missing, Status.DONE, "user"),
        (ready, Status.DONE, "user"),
        (drafted, Status.DONE, "agent"),
        (drafted, Status.NA, "agent"),
        (done, Status.DRAFTED, "agent"),
        (later, Status.READY, "ema"),
        (missing, Status.LATER, "ema"),
        (missing, Status.LATER, "user"),
    ):
        _code(lambda s=state, t=target, a=actor: transition(s, t, a))
    assert (
        transition(missing, Status.LATER, "ema", "map absent", auto_later=True).status
        == Status.LATER
    )
    _code(lambda: transition(missing, Status.NA, "ema"))


def test_materials_status_decisions_undo_and_supersession(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    record_material(ws, job, MaterialKind.METER, False, "synthetic intake")
    later = set_status(ws, job, "ch5.electric", Status.LATER, "ema", "meter absent")
    assert later.status == Status.LATER
    _code(lambda: set_status(ws, job, "ch5.termic", Status.LATER, "ema", "wrong material"))
    record_material(ws, job, MaterialKind.METER, True, "synthetic intake")
    propose(ws, job, "visit.date", "2026-09-27", [], state="extracted")
    recompute_ready(ws, job)
    assert get_status(ws, job, "ch5.electric").status == Status.READY
    drafted = mark_drafted(ws, job, "ch5.electric", "agent", ("fact:load",))
    set_status(ws, job, "ch5.electric", Status.DONE, "user")
    decision = log(ws, job)[-1]
    assert decision.target_kind == "section" and decision.on_revision == drafted.revision
    undo(ws, job, decision.id, "user")
    assert get_status(ws, job, "ch5.electric").status == Status.DRAFTED
    set_status(ws, job, "ch5.electric", Status.DONE, "user")
    decision = log(ws, job)[-1]
    stale = mark_stale(ws, job, "ch5.electric", "fact:load")
    assert stale.status == Status.DRAFTED and stale.stale
    assert log(ws, job)[-1].detail == "fact:load"
    _code(lambda: undo(ws, job, decision.id, "user"), "decision_superseded")
    assert not mark_drafted(ws, job, "ch5.electric", "agent", ("fact:load",)).stale
    assert set_status(ws, job, "ch5.electric", Status.DONE, "user").status == Status.DONE
    _code(lambda: decide(ws, job, "ch5.electric", "accept", 1, "agent"), "field_missing")


def test_user_can_undo_own_done_decision_to_drafted(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch1", "agent", ())
    set_status(ws, job, "ch1", Status.DONE, "user")
    decision = log(ws, job)[-1]

    undo(ws, job, decision.id, "user")

    assert get_status(ws, job, "ch1").status == Status.DRAFTED


def test_user_undo_restores_drafted_as_stale_when_input_changed(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch1", "agent", ("fact:load",))
    set_status(ws, job, "ch1", Status.DONE, "user")
    decision = log(ws, job)[-1]
    propose(ws, job, "load", 10, [], state="extracted")

    undo(ws, job, decision.id, "user")

    state = get_status(ws, job, "ch1")
    assert state.status == Status.DRAFTED and state.stale
    assert state.changed_input == "fact:load"


def test_agent_cannot_undo_user_done_decision(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch1", "agent", ())
    set_status(ws, job, "ch1", Status.DONE, "user")
    decision = log(ws, job)[-1]

    _code(lambda: undo(ws, job, decision.id, "agent"))
    assert get_status(ws, job, "ch1").status == Status.DONE


def test_mark_stale_is_idempotent_and_logs_once(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch1", "agent", ("fact:load",))

    first = mark_stale(ws, job, "ch1", "fact:load")
    entries_after_first = len(log(ws, job))
    second = mark_stale(ws, job, "ch1", "fact:load")

    assert first.stale and second.stale
    assert len(log(ws, job)) == entries_after_first == 2
    assert [entry.actor for entry in log(ws, job)] == ["agent", "ema"]


def test_readiness_lists_unknown_stale_conflict_and_complete(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    initial = audit_readiness(ws, job)
    assert not initial.final_ok and len(initial.blocking) >= len(CATALOGUE)
    assert any("aşteaptă preluarea dosarului" in item for item in initial.next)
    for section in CATALOGUE:
        set_status(ws, job, section.id, Status.NA, "user")
    assert {issue.code for issue in audit_readiness(ws, job).blocking} == {"chapter_empty"}
    propose(ws, job, AuditFact.COMPANY_NAME.value, "A", [], state="extracted")
    propose(ws, job, AuditFact.COMPANY_NAME.value, "B", [], state="extracted")
    assert any(issue.code == "conflict" for issue in audit_readiness(ws, job).blocking)


def test_carrier_facts_use_shared_energy_key_and_conditions(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    key = field_key("carrier", Carrier.electricity_grid, 2025)
    propose(ws, job, key, 10, [], state="extracted")
    recompute_ready(ws, job)
    assert get_status(ws, job, "ch4.electricitate").status == Status.READY
    assert get_status(ws, job, "ch4.gaz").status == Status.MISSING
    unknown = Condition("fact", AuditFact.FLEET.value)
    assert applies(Condition("any", children=(unknown, Condition("always"))), {}, {}) is True
    assert applies(Condition("all", children=(unknown, Condition("always"))), {}, {}) is None


def test_material_change_marks_fingerprinted_done_stale(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    record_material(ws, job, MaterialKind.METER, True, "first")
    propose(ws, job, "visit.date", "2026-09-27", [], state="extracted")
    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch5.electric", "agent", ("material:meter_photos",))
    set_status(ws, job, "ch5.electric", Status.DONE, "user")
    record_material(ws, job, MaterialKind.METER, True, "replacement")
    state = get_status(ws, job, "ch5.electric")
    assert state.status == Status.DRAFTED and state.stale
    assert log(ws, job)[-1].detail == "material:meter_photos"


def test_later_waits_for_material_and_first_arrival_invalidates_draft(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    record_material(ws, job, MaterialKind.MAP, False, "missing")
    set_status(ws, job, "ch2.localizare", Status.LATER, "ema", "map absent")
    recompute_ready(ws, job)
    assert get_status(ws, job, "ch2.localizare").status == Status.LATER
    record_material(ws, job, MaterialKind.MAP, True, "arrived")
    recompute_ready(ws, job)
    assert get_status(ws, job, "ch2.localizare").status == Status.MISSING

    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch1", "agent", ("material:visit_photos",))
    record_material(ws, job, MaterialKind.VISIT, True, "first arrival")
    assert get_status(ws, job, "ch1").stale


def test_new_material_requires_human_recheck_of_prior_na(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    for section in CATALOGUE:
        set_status(ws, job, section.id, Status.NA, "user")
    assert {issue.code for issue in audit_readiness(ws, job).blocking} == {"chapter_empty"}
    record_material(ws, job, MaterialKind.METER, True, "received")
    assert any(issue.code == "na_recheck" for issue in audit_readiness(ws, job).blocking)
    set_status(ws, job, "ch5.electric", Status.NA, "user", "not used for this job")
    assert get_status(ws, job, "ch5.electric").na_applicable is True


def test_corrected_fact_stales_done_and_refuses_final_export(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    field = propose(ws, job, AuditFact.COMPANY_NAME.value, "Old", [], state="extracted")
    recompute_ready(ws, job)
    for section in CATALOGUE:
        if section.id != "ch2.date_generale":
            set_status(ws, job, section.id, Status.NA, "user")
    mark_drafted(ws, job, "ch2.date_generale", "agent", ())
    set_status(ws, job, "ch2.date_generale", Status.DONE, "user")
    assert {issue.code for issue in audit_readiness(ws, job).blocking} == {"chapter_empty"}
    decide(ws, job, field.id, "correct", field.revision, "user", value="New")
    readiness = audit_readiness(ws, job)
    assert not readiness.final_ok and any(issue.code == "stale" for issue in readiness.blocking)
    state = get_status(ws, job, "ch2.date_generale")
    assert state.status == Status.DRAFTED and state.stale
    assert log(ws, job)[-1].detail == f"fact:{AuditFact.COMPANY_NAME.value}"
    revision = state.revision
    audit_readiness(ws, job)
    assert get_status(ws, job, "ch2.date_generale").revision == revision

    mark_drafted(ws, job, "ch2.date_generale", "agent", ())
    set_status(ws, job, "ch2.date_generale", Status.DONE, "user")
    with ws.connect() as db:
        row = db.execute("SELECT data FROM fields WHERE id=?", (field.id,)).fetchone()
    corrected = Field.model_validate_json(row["data"])
    decide(ws, job, field.id, "correct", corrected.revision, "user", value="Newest")
    with ws.connect() as db:
        db.execute(
            "INSERT INTO runs(id,job_id,stage,owner,state,started_at,ended_at) "
            "VALUES ('unused',?,'audit_final','synthetic','ready','2026-01-01','2026-01-01')",
            (job,),
        )
        db.execute(
            "INSERT INTO outputs (id,job_id,run_id,relative_path,sha,size,kind,seq) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("final", job, "unused", "outputs/final.docx", "unused", 0, "final", 1),
        )
    _code(
        lambda: export(
            ws, job, AuditWorkflow(), final=True, dest=tmp_path / "final.docx", actor="user"
        ),
        "not_ready",
    )
    assert get_status(ws, job, "ch2.date_generale").stale


def test_agent_cannot_undo_human_na_back_to_done(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch1", "agent", ())
    set_status(ws, job, "ch1", Status.DONE, "user")
    set_status(ws, job, "ch1", Status.NA, "user", "not applicable")
    decision = log(ws, job)[-1]
    _code(lambda: undo(ws, job, decision.id, "agent"))
    assert get_status(ws, job, "ch1").status == Status.NA
    undo(ws, job, decision.id, "user")
    assert get_status(ws, job, "ch1").status == Status.DONE


def test_concurrent_material_update_cannot_leave_done_current(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    record_material(ws, job, MaterialKind.METER, True, "first")
    propose(ws, job, "visit.date", "2026-09-27", [], state="extracted")
    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch5.electric", "agent", ())
    barrier = Barrier(2)

    def change_material() -> None:
        barrier.wait()
        record_material(ws, job, MaterialKind.METER, True, "replacement")

    def approve() -> None:
        barrier.wait()
        try:
            set_status(ws, job, "ch5.electric", Status.DONE, "user")
        except EmaError as error:
            assert error.code in ("transition_forbidden", "stale_revision")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(change_material), executor.submit(approve)]
        for future in futures:
            future.result()
    state = get_status(ws, job, "ch5.electric")
    assert state.status == Status.DRAFTED and state.stale


def test_cli_done_confirmation_and_noninteractive_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job = _job(tmp_path)
    monkeypatch.setenv("EMA_WORKSPACE", str(ws.root))
    runner = CliRunner()
    listing = runner.invoke(_app, ["job", "sections", job])
    assert listing.exit_code == 0 and "ID | Stare | Secţiune | Motiv" in listing.output
    assert "ch1 | missing |" in listing.output
    monkeypatch.setattr(cli_review, "_terminal", lambda: False)
    refused = runner.invoke(_app, ["job", "section", job, "ch1", "done"])
    assert isinstance(refused.exception, EmaError)
    assert refused.exception.code == "confirmation_requires_terminal"
    na_refused = runner.invoke(_app, ["job", "section", job, "ch1", "n/a"])
    assert isinstance(na_refused.exception, EmaError)
    assert na_refused.exception.code == "confirmation_requires_terminal"
    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch1", "ema", ())
    monkeypatch.setattr(cli_review, "_terminal", lambda: True)
    rejected = runner.invoke(_app, ["job", "section", job, "ch1", "done"], input="n\n")
    assert rejected.exit_code == 2
    accepted = runner.invoke(_app, ["job", "section", job, "ch1", "done"], input="y\n")
    assert accepted.exit_code == 0, accepted.output
    assert accepted.output.count("[y/N]") == 1
    assert get_status(ws, job, "ch1").status == Status.DONE


def test_empty_chapter_refuses_final_but_allows_draft(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    recompute_ready(ws, job)
    mark_drafted(ws, job, "ch2", "ema", ())
    set_status(ws, job, "ch2", Status.DONE, "user")
    for section in CATALOGUE:
        if section.id != "ch2":
            set_status(ws, job, section.id, Status.NA, "user")
    readiness = audit_readiness(ws, job)
    assert readiness.draft_ok and not readiness.final_ok
    chapter = next(section for section in CATALOGUE if section.id == "ch2")
    assert any(
        issue.code == "chapter_empty"
        and issue.message
        == f"{chapter.title}: capitolul nu are conținut".translate(str.maketrans("șțȘȚ", "şţŞŢ"))
        for issue in readiness.blocking
    )
    _code(lambda: AuditWorkflow().start_final(ws, job), "not_ready")
