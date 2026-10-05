"""Final audit readiness includes unresolved narrative fields."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from PIL import Image
from tests.audit_structure import RETAINED_CONTENT, confirm_retained_content
from tests.workspace_jobs import create_job

from ema.audit.applicability import fact_fields
from ema.audit.catalogue import CATALOGUE
from ema.audit.catalogue_types import PrefixPattern
from ema.audit.content_checks import _has_arithmetic_conclusion, content_issues, total_blockers
from ema.audit.sections import Status, set_status
from ema.audit.workflow import AuditWorkflow
from ema.core.review import decide, mark_absent, propose
from ema.core.review.models import Field, FieldSpec
from ema.core.workspace import Workspace
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import AUDIT_FACTORS_2026
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading


def _job(tmp_path: Path) -> tuple[Workspace, str]:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    confirm_retained_content(ws, job)
    for section in CATALOGUE:
        if section.id not in RETAINED_CONTENT:
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


def test_arithmetic_conclusion_uses_reviewed_carrier_values() -> None:
    reading = Field(
        id="energy",
        job_id="synthetic",
        key="carrier.electricity_grid.2025",
        label="Electricitate",
        value_type="number",
        unit="MWh",
        value=Decimal(10),
        state="supplied",
        presence="found",
        evidence=["source"],
    )
    assert _has_arithmetic_conclusion({reading.key: reading})
    rejected = reading.model_copy(update={"review": "rejected"})
    assert not _has_arithmetic_conclusion({rejected.key: rejected})


def test_total_blockers_only_lists_counted_carriers_with_missing_tep() -> None:
    dataset = EnergyDataset(
        (2024,),
        {
            Carrier.lpg: {2024: CarrierSeries(annual=Reading(None, "t"))},
            Carrier.electricity_grid: {2024: CarrierSeries(annual=Reading(10, "MWh"))},
            Carrier.water_potable: {2024: CarrierSeries(annual=Reading(None, "m3"))},
            Carrier.electricity_cogen: {2024: CarrierSeries(annual=Reading(None, "MWh"))},
        },
    )
    assert total_blockers(dataset, AUDIT_FACTORS_2026) == [(Carrier.lpg, 2024)]
    complete = EnergyDataset(
        (2024,),
        {Carrier.electricity_grid: {2024: CarrierSeries(annual=Reading(10, "MWh"))}},
    )
    assert total_blockers(complete, AUDIT_FACTORS_2026) == []


def test_total_blocker_issues_point_to_carrier_fields_and_replace_ch4_gap(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    gas = mark_absent(
        ws,
        job,
        FieldSpec(
            key="carrier.natural_gas.2024", label="Gaze naturale", value_type="number", unit="MWh"
        ),
        "not_found",
    )
    monthly = mark_absent(
        ws,
        job,
        FieldSpec(key="carrier.lpg.2024.01", label="GPL ianuarie", value_type="number", unit="t"),
        "not_found",
    )
    mark_absent(
        ws,
        job,
        FieldSpec(key="carrier.lpg.2024.02", label="GPL februarie", value_type="number", unit="t"),
        "not_found",
    )
    annual = mark_absent(
        ws,
        job,
        FieldSpec(key="carrier.lpg.2025", label="GPL", value_type="number", unit="t"),
        "not_found",
    )
    mark_absent(
        ws,
        job,
        FieldSpec(key="carrier.lpg.2025.01", label="GPL ianuarie", value_type="number", unit="t"),
        "not_found",
    )
    mark_absent(ws, job, "narrative.ch4.concluzii", "not_found")
    other = mark_absent(ws, job, "narrative.ch5.summary", "not_found")
    with ws.connect() as db:
        assert [
            (issue.code, issue.field_id, issue.message) for issue in content_issues(db, job)
        ] == [
            (
                "data_total_blocked",
                monthly.id,
                "Totalul de energie din 2024 lipseşte: completaţi cantitatea de GPL.",
            ),
            (
                "data_total_blocked",
                gas.id,
                "Totalul de energie din 2024 lipseşte: completaţi cantitatea de gaze naturale.",
            ),
            (
                "data_total_blocked",
                annual.id,
                "Totalul de energie din 2025 lipseşte: completaţi cantitatea de GPL.",
            ),
            ("narrative_missing", other.id, "Textul lipseşte: narrative.ch5.summary"),
        ]
