"""Compare a recorded vision replay with the local human-checked panel answer key."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import artifacts_path
from tests.workspace_jobs import create_job

from ema.audit.chapter_five import run_measurements
from ema.audit.readings import run_readings
from ema.audit.visit import run_visit, slug
from ema.core.review import decide, fields
from ema.core.review.models import Field
from ema.core.workspace import Workspace

pytestmark = [pytest.mark.golden, pytest.mark.word]


def _tuple(entry: dict[str, Any]) -> tuple[str, str, str, str | None]:
    return (
        str(entry["quantity"]),
        str(entry["phase"]),
        str(entry["value"]).replace(",", "."),
        entry.get("unit"),
    )


def _actual(field: Field) -> tuple[str, str, str, str | None]:
    quantity, phase = field.key.split(".")[-2:]
    return quantity, phase, str(field.value).replace(",", "."), field.unit


def _compare(
    expected: dict[str, Any], actual: set[tuple[str, str, str, str | None]]
) -> tuple[int, int, int]:
    required = {_tuple(entry) for entry in expected.get("values", [])}
    missing = required - actual
    ranges = expected.get("ranges", [])
    missing_ranges = [
        entry
        for entry in ranges
        if not any(
            quantity == entry["quantity"]
            and phase == entry["phase"]
            and unit == entry.get("unit")
            and Decimal(str(entry["min"]).replace(",", "."))
            <= Decimal(value)
            <= Decimal(str(entry["max"]).replace(",", "."))
            for quantity, phase, value, unit in actual
        )
    ]
    extra = [
        item
        for item in actual - required
        if not any(
            item[0] == entry["quantity"]
            and item[1] == entry["phase"]
            and item[3] == entry.get("unit")
            and Decimal(str(entry["min"]).replace(",", "."))
            <= Decimal(item[2])
            <= Decimal(str(entry["max"]).replace(",", "."))
            for entry in ranges
        )
    ]
    return (
        len(required) - len(missing) + len(ranges) - len(missing_ranges),
        len(missing) + len(missing_ranges),
        len(extra),
    )


def test_recorded_panel_readings_match_human_key(reference_library: Path, tmp_path: Path) -> None:
    default_key = (
        reference_library / "audit/cases/audit-case-b/visit/electrical/answer-key.json"
    )
    answer_key = Path(os.environ.get("EMA_S15_ANSWER_KEY", str(default_key)))
    if not answer_key.is_file():
        pytest.skip("S15a answer key missing: EMA_S15_ANSWER_KEY")
    name = os.environ.get("EMA_S15_VISION_RECORDING")
    if not name or not Path(name).is_file():
        pytest.skip("S15a recorded vision replay missing: EMA_S15_VISION_RECORDING")
    recording = Path(name)
    recorded = json.loads(recording.read_text(encoding="utf-8"))
    assert recorded.get("source") == "recorded", "S15a recording must have source=recorded"
    key = json.loads(answer_key.read_text(encoding="utf-8"))
    assert key["version"] == 2 and key["level"] == "panel"

    visit = reference_library / "audit/cases/audit-case-b/visit"
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    panels = sorted((visit / "electrical").glob("tablou-electric-*"))
    for panel in panels:
        for photo in panel.glob("*.jpeg"):
            ws.set_slot(
                job, f"visit/meter/{panel.name}/{photo.name}", ws.add_file("synthetic", photo)
            )
    run_visit(ws, job)
    result = run_readings(ws, job, recording=recording)
    assert result.photos_read == 36 and result.photos_failed == 0
    readings = [
        field
        for field in fields(ws, job)
        if field.key.startswith("meter.") and field.key.count(".") == 4
    ]
    assert readings and all(field.needs_confirmation for field in readings)
    for field in readings:
        decide(ws, job, field.id, "accept", field.revision, "user")
    accepted = [field for field in fields(ws, job) if field.id in {item.id for item in readings}]
    assert all(field.review == "accepted" and not field.needs_confirmation for field in accepted)

    report: list[dict[str, str | int]] = []
    for panel in key["panels"]:
        folder = panel.get("folder")
        if folder is None:
            report.append({"folder": "unmapped", "matched": 0, "missing": 0, "extra": 0})
            continue
        group = {
            _actual(field)
            for field in accepted
            if field.key.startswith(f"meter.{slug(str(folder))}.")
        }
        matched, missing, extra = _compare(panel, group)
        report.append(
            {"folder": str(folder), "matched": matched, "missing": missing, "extra": extra}
        )
    output = artifacts_path("s15a", "answer-key-counts.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    message = "panel-level answer key mismatch; see local count report"
    assert all(row["missing"] == 0 for row in report), message
    measurements = run_measurements(ws, job)
    assert measurements.figures == 36
