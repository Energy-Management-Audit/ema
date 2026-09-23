"""Undo safety and monotonic Jurnal ordering."""

from __future__ import annotations

import importlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_review import FakeWorkflow, evidence, get

from ema.core.errors import EmaError
from ema.core.jobs import create_job
from ema.core.review import (
    approve_final,
    base_readiness,
    decide,
    log,
    propose,
    readiness_hash,
    undo,
)
from ema.core.workspace import Workspace


def test_undo_refuses_to_drop_stage_candidate(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    field = propose(ws, job, "source", 10, [evidence("first")], state="extracted")
    correction = decide(ws, job, field.id, "correct", field.revision, "user", value=11)
    rerun = propose(ws, job, "source", 10, [evidence("rerun")], state="extracted")
    with pytest.raises(EmaError) as caught:
        undo(ws, job, correction.id, "user")
    assert caught.value.code == "field_changed"
    assert caught.value.detail == str(rerun.revision)
    assert get(ws, job, "source") == rerun
    assert len(log(ws, job)) == 1


def test_undo_allows_chain_explained_by_decisions(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    field = propose(ws, job, "source", 10, [evidence("first")], state="extracted")
    first = decide(ws, job, field.id, "correct", field.revision, "user", value=11)
    second = decide(ws, job, field.id, "correct", first.after.revision, "user", value=12)
    undo(ws, job, second.id, "user")
    undo(ws, job, first.id, "user")
    assert get(ws, job, "source").value == 10


def test_undo_of_undo_restores_supersession(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    field = propose(ws, job, "source", 10, [evidence("first")], state="extracted")
    first = decide(ws, job, field.id, "correct", field.revision, "user", value=11)
    second = decide(ws, job, field.id, "correct", first.after.revision, "user", value=12)
    reversal = undo(ws, job, second.id, "user")
    undo(ws, job, reversal.id, "user")
    with pytest.raises(EmaError) as caught:
        undo(ws, job, first.id, "user")
    assert caught.value.code == "decision_superseded"
    assert caught.value.detail == second.id
    assert get(ws, job, "source").value == 12


def test_equal_timestamps_keep_insertion_order_for_undo_and_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    field = propose(ws, job, "source", 10, [evidence("first")], state="extracted")
    module = importlib.import_module("ema.core.review.fields")

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            return datetime(2026, 1, 1, tzinfo=UTC)

    original_uuid4 = uuid.uuid4
    ids = iter(("ffffffffffffffffffffffffffffffff", "00000000000000000000000000000000"))

    def descending_ids():  # type: ignore[no-untyped-def]
        try:
            return SimpleNamespace(hex=next(ids))
        except StopIteration:
            return original_uuid4()

    monkeypatch.setattr(module, "datetime", FrozenDatetime)
    monkeypatch.setattr(module.uuid, "uuid4", descending_ids)
    first = decide(ws, job, field.id, "accept", field.revision, "user")
    second = decide(ws, job, field.id, "reject", first.after.revision, "user")
    assert first.at == second.at
    assert [item.id for item in log(ws, job)] == [first.id, second.id]
    with pytest.raises(EmaError) as caught:
        undo(ws, job, first.id, "user")
    assert caught.value.code == "decision_superseded" and caught.value.detail == second.id

    class Workflow(FakeWorkflow):
        def readiness(self, ws: Workspace, job: str):  # type: ignore[no-untyped-def]
            return base_readiness(ws, job, [])

    workflow = Workflow()
    output = workflow.render(ws, job, "final")
    approval = approve_final(
        ws, job, output, readiness_hash(ws, job, workflow.readiness(ws, job), workflow), "user"
    )
    assert approval.on_decision == second.id
