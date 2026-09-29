"""Visit registration against the local CLIENT-A2 folder inventory, without vision calls."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.audit.applicability import applies
from ema.audit.catalogue import CATALOGUE, MaterialKind
from ema.audit.readings import run_readings
from ema.audit.visit import run_visit
from ema.core.errors import EmaError
from ema.core.review import fields
from ema.core.workspace import Workspace

pytestmark = [pytest.mark.golden, pytest.mark.word]


def test_CLIENT-A2_visit_inventory_and_disabled_vision(
    reference_library: Path, tmp_path: Path
) -> None:
    visit = reference_library / "audit/cases/audit-case-b/visit"
    panels = sorted((visit / "electrical").glob("tablou-electric-*"))
    thermal = sorted((visit / "thermography").glob("*.jpeg"))
    assert [len(list(panel.glob("*.jpeg"))) for panel in panels] == [4, 9, 8, 15]
    assert len(thermal) == 26

    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    for panel in panels:
        for photo in panel.glob("*.jpeg"):
            ws.set_slot(
                job, f"visit/meter/{panel.name}/{photo.name}", ws.add_file("synthetic", photo)
            )
    for photo in thermal:
        ws.set_slot(job, f"visit/thermal/{photo.name}", ws.add_file("synthetic", photo))
    result = run_visit(ws, job)
    assert (result.panels, result.meter_photos, result.thermal_images) == (4, 36, 26)
    assert not result.failures
    with ws.connect() as db:
        materials = {
            row["kind"]: bool(row["present"])
            for row in db.execute("SELECT kind,present FROM audit_materials WHERE job_id=?", (job,))
        }
    assert materials[MaterialKind.METER.value] and materials[MaterialKind.THERMAL.value]
    sections = {section.id: section for section in CATALOGUE}
    for section_id in ("ch5.electric_fisa", "ch5.electric_rezultate", "ch5.termic_fisa"):
        assert applies(sections[section_id].applies_when, materials, {}) is True
    missing = {field.key for field in fields(ws, job) if field.value is None}
    assert "visit.date" in missing
    assert {f"meter.{panel.name}.device" for panel in panels} <= missing

    with pytest.raises(EmaError) as caught:
        run_readings(ws, job, recording=None)
    assert caught.value.code == "ai_client_disabled"
    with ws.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM llm_calls WHERE job_id=?", (job,)).fetchone()[0] == 0
        )
