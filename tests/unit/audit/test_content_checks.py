"""Final audit readiness includes unresolved narrative fields."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ema.audit.applicability import fact_fields
from ema.audit.catalogue import CATALOGUE
from ema.audit.catalogue_types import PrefixPattern
from ema.audit.content_checks import content_issues
from ema.audit.sections import Status, set_status
from ema.audit.workflow import AuditWorkflow
from ema.core.jobs import create_job
from ema.core.review import decide, mark_absent, propose
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace


def _job(tmp_path: Path) -> tuple[Workspace, str]:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    for section in CATALOGUE:
        set_status(ws, job, section.id, Status.NA, "user")
    return ws, job


def test_narrative_gap_blocks_final_until_corrected(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    field = mark_absent(
        ws,
        job,
        FieldSpec(key="narrative.ch5.panel-1.p1", label="Rezultate termice", value_type="text"),
        "not_found",
    )
    readiness = AuditWorkflow().readiness(ws, job)
    assert readiness.draft_ok
    assert not readiness.final_ok
    assert [(issue.code, issue.field_id, issue.message) for issue in readiness.blocking] == [
        ("narrative_missing", field.id, "Textul lipseşte: Rezultate termice")
    ]
    assert readiness.next == ["Textul lipseşte: Rezultate termice"]

    decide(ws, job, field.id, "correct", field.revision, "user", value="Text verificat")
    with ws.connect() as db:
        readiness = AuditWorkflow().readiness_in_tx(ws, job, db)
    assert readiness.final_ok
    assert readiness.draft_ok


def test_measure_narratives_are_scoped_by_current_count(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    first = mark_absent(ws, job, "narrative.ch6.measure.1", "not_found")
    second = mark_absent(ws, job, "narrative.ch6.measure.2", "not_found")
    with ws.connect() as db:
        assert [issue.field_id for issue in content_issues(db, job)] == [first.id, second.id]

    propose(
        ws,
        job,
        FieldSpec(key="audit_measure.count", label="Număr măsuri", value_type="number"),
        1,
        [],
        state="supplied",
    )
    with ws.connect() as db:
        assert [issue.field_id for issue in content_issues(db, job)] == [first.id]


def test_prefix_pattern_returns_fields_in_key_order(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    later = mark_absent(ws, job, "narrative.ch5.z", "not_found")
    earlier = mark_absent(ws, job, "narrative.ch5.a", "not_found")
    assert fact_fields(
        PrefixPattern("narrative.ch5."),
        {later.key: later, earlier.key: earlier},
    ) == [earlier, later]


def test_only_active_photo_readings_block_final(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    image = tmp_path / "meter.png"
    Image.new("RGB", (8, 8)).save(image)
    sha = ws.add_file("synthetic", image)
    slot = "visit/meter/panel/meter.png"
    version = ws.set_slot(job, slot, sha)
    reading = propose(
        ws,
        job,
        f"meter.panel.{sha[:8]}.current.l1",
        5,
        [],
        state="extracted",
        needs_confirmation=True,
    )
    with ws.connect() as db:
        assert [(issue.code, issue.field_id) for issue in content_issues(db, job)] == [
            ("reading_unconfirmed", reading.id)
        ]
    ws.remove_version(job, slot, version.version)
    with ws.connect() as db:
        assert content_issues(db, job) == []


def test_active_panel_device_needs_individual_confirmation(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    image = tmp_path / "device.png"
    Image.new("RGB", (8, 8)).save(image)
    slot = "visit/meter/Panel 1/device.png"
    version = ws.set_slot(job, slot, ws.add_file("synthetic", image))
    device = propose(
        ws,
        job,
        FieldSpec(key="meter.panel-1.device", label="Aparat", value_type="text"),
        "Synthetic meter",
        [],
        state="extracted",
        needs_confirmation=True,
    )
    readiness = AuditWorkflow().readiness(ws, job)
    assert not readiness.final_ok
    assert [(issue.code, issue.field_id) for issue in readiness.blocking] == [
        ("reading_unconfirmed", device.id)
    ]
    decide(ws, job, device.id, "accept", device.revision, "user")
    assert AuditWorkflow().readiness(ws, job).final_ok
    ws.remove_version(job, slot, version.version)
    with ws.connect() as db:
        assert content_issues(db, job) == []
