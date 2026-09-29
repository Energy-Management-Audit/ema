"""Chapter five uses active photos and human-confirmed values only."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

import ema.audit.chapter_five as chapter_five_module
import ema.audit.publication as publication_module
from ema.audit.chapter_five import chapter_five_plan, run_measurements, start_measurements
from ema.audit.sections import Status, audit_readiness, get_status
from ema.audit.visit import run_visit
from ema.core.jobs import create_job, status, subscribe
from ema.core.review import decide, fields, propose
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace


def test_pending_marker_and_out_of_norm_narrative(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    image = tmp_path / "screen.png"
    Image.new("RGB", (12, 8), "white").save(image)
    sha = ws.add_file("synthetic", image)
    ws.set_slot(job, "visit/meter/Panel 1/screen.png", sha)
    run_visit(ws, job)
    key = f"meter.panel-1.{sha[:8]}.voltage_ln.l1"
    reading = propose(
        ws,
        job,
        FieldSpec(key=key, label="U1", value_type="number", unit="V", chapter="ch5.electric_fisa"),
        "260",
        [],
        state="extracted",
        needs_confirmation=True,
    )
    pending = chapter_five_plan(ws, job)
    assert pending.panels[0].photos[0].readings[0].value is None
    assert pending.panels[0].photos[0].norm is None
    assert pending.panels[0].photos[0].narrative_key is None

    decide(ws, job, reading.id, "accept", reading.revision, "user")
    confirmed = chapter_five_plan(ws, job)
    photo = confirmed.panels[0].photos[0]
    assert photo.readings[0].value == "260"
    assert photo.norm is None
    narrative_key = f"narrative.ch5.panel-1.{sha[:8]}"
    assert photo.narrative_key == narrative_key
    result = run_measurements(ws, job)
    assert result.missing_narratives >= 3
    assert narrative_key in {field.key for field in fields(ws, job) if field.value is None}
    assert result.plan_path.is_file()


def test_confirmed_in_range_has_norm_without_interpretation(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    image = tmp_path / "screen.png"
    Image.new("RGB", (12, 8), "white").save(image)
    sha = ws.add_file("synthetic", image)
    ws.set_slot(job, "visit/meter/Panel 1/screen.png", sha)
    run_visit(ws, job)
    key = f"meter.panel-1.{sha[:8]}.voltage_ln.l1"
    reading = propose(
        ws,
        job,
        FieldSpec(key=key, label="U1", value_type="number", unit="V"),
        "230",
        [],
        state="extracted",
        needs_confirmation=True,
    )
    decide(ws, job, reading.id, "accept", reading.revision, "user")
    photo = chapter_five_plan(ws, job).panels[0].photos[0]
    assert photo.norm == "voltage"
    assert photo.narrative_key is None


def test_confirmation_and_new_photo_stale_measurements(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    image = tmp_path / "screen.png"
    Image.new("RGB", (12, 8), "white").save(image)
    sha = ws.add_file("synthetic", image)
    slot = "visit/meter/Panel 1/screen.png"
    ws.set_slot(job, slot, sha)
    run_visit(ws, job)
    key = f"meter.panel-1.{sha[:8]}.voltage_ln.l1"
    reading = propose(
        ws,
        job,
        FieldSpec(key=key, label="U1", value_type="number", unit="V"),
        "230",
        [],
        state="extracted",
        needs_confirmation=True,
    )
    run_measurements(ws, job)
    before = get_status(ws, job, "ch5.electric_fisa")
    assert before.status == Status.DRAFTED and not before.stale
    decide(ws, job, reading.id, "accept", reading.revision, "user")
    audit_readiness(ws, job)
    after = get_status(ws, job, "ch5.electric_fisa")
    assert after.stale
    run_measurements(ws, job)
    assert not get_status(ws, job, "ch5.electric_fisa").stale
    Image.new("RGB", (12, 8), "black").save(image)
    replacement = ws.add_file("synthetic", image)
    ws.set_slot(job, slot, replacement)
    run_visit(ws, job)
    assert get_status(ws, job, "ch5.electric_fisa").stale


def test_measurements_uses_one_snapshot_for_plan_and_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    image = tmp_path / "screen.png"
    Image.new("RGB", (12, 8), "white").save(image)
    sha = ws.add_file("synthetic", image)
    ws.set_slot(job, "visit/meter/Panel 1/screen.png", sha)
    run_visit(ws, job)
    reading = propose(
        ws,
        job,
        FieldSpec(key=f"meter.panel-1.{sha[:8]}.voltage_ln.l1", label="U1", value_type="number"),
        "260",
        [],
        state="extracted",
        needs_confirmation=True,
    )
    decide(ws, job, reading.id, "accept", reading.revision, "user")
    original_fields = chapter_five_module.fields
    original_draft = publication_module.mark_drafted
    reads = 0
    fingerprints: list[tuple[str, ...]] = []

    def once(*args: object, **kwargs: object) -> object:
        nonlocal reads
        reads += 1
        if reads > 1:
            raise AssertionError("measurements reread fields after building its plan")
        return original_fields(*args, **kwargs)  # type: ignore[arg-type]

    def capture(*args: object, **kwargs: object) -> object:
        fingerprints.append(args[4])  # type: ignore[arg-type]
        return original_draft(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(chapter_five_module, "fields", once)
    monkeypatch.setattr(publication_module, "mark_drafted", capture)
    run = start_measurements(ws, job)
    for _ in subscribe(ws, job):
        pass
    assert next(item for item in status(ws, job).runs if item["id"] == run)["state"] == "ready"
    assert reads == 1
    key = f"fact:narrative.ch5.panel-1.{sha[:8]}"
    assert any(key in fingerprint for fingerprint in fingerprints)
