"""Visit registration groups photos and tracks exact material revisions."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from ema.audit.visit import run_visit, slug, visit_view
from ema.core.errors import EmaError
from ema.core.jobs import create_job
from ema.core.review import decide, fields, propose
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace


def _job(tmp_path: Path) -> tuple[Workspace, str]:
    ws = Workspace(tmp_path / "workspace")
    return ws, create_job(ws, "audit", "synthetic", 2026)


def _slot(ws: Workspace, job: str, path: Path, slot: str) -> None:
    ws.set_slot(job, slot, ws.add_file("synthetic", path))


def test_nested_visit_slots_and_grouping(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    one = tmp_path / "one.png"
    two = tmp_path / "two.png"
    Image.new("RGB", (12, 8), "white").save(one)
    Image.new("RGB", (12, 8), "black").save(two)
    _slot(ws, job, one, "visit/meter/Tablou electric 1/display10.png")
    _slot(ws, job, two, "visit/meter/Tablou electric 1/display2.png")
    _slot(ws, job, one, "visit/thermal/thermal.png")
    result = run_visit(ws, job)
    assert (result.panels, result.meter_photos, result.thermal_images, result.failures) == (
        1,
        2,
        1,
        (),
    )
    panel = visit_view(ws, job).panels[0]
    assert panel.id == slug("Tablou electric 1") == "tablou-electric-1"
    assert [photo.name for photo in panel.photos] == ["display2.png", "display10.png"]
    absent = {field.key for field in fields(ws, job) if field.value is None}
    assert {"visit.date", "meter.tablou-electric-1.device"} <= absent
    assert run_visit(ws, job).failures == ()


def test_invalid_image_is_item_failure_and_missing_visit_is_error(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    with pytest.raises(EmaError) as caught:
        run_visit(ws, job)
    assert caught.value.code == "visit_missing"
    bad = tmp_path / "bad.png"
    bad.write_text("not an image", encoding="utf-8")
    _slot(ws, job, bad, "visit/meter/Panel/bad.png")
    assert run_visit(ws, job).failures == ("visit_not_image:visit/meter/Panel/bad.png",)


def test_visit_slot_validation_keeps_other_prefixes_restricted(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    path = tmp_path / "photo.png"
    Image.new("RGB", (8, 8)).save(path)
    sha = ws.add_file("synthetic", path)
    ws.set_slot(job, "visit/meter/panel/photo.png", sha)
    for slot in (
        "visit/meter/panel/nested/photo.png",
        "visit/meter/../photo.png",
        "visit/meter/panel/../../photo.png",
        "other/meter/panel/photo.png",
    ):
        with pytest.raises(EmaError) as caught:
            ws.set_slot(job, slot, sha)
        assert caught.value.code == "invalid_slot"


def test_rerun_visit_keeps_confirmed_device(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    image = tmp_path / "meter.png"
    Image.new("RGB", (8, 8)).save(image)
    _slot(ws, job, image, "visit/meter/Panel 1/meter.png")
    run_visit(ws, job)
    device = propose(
        ws,
        job,
        FieldSpec(key="meter.panel-1.device", label="Aparat", value_type="text"),
        "Synthetic meter",
        [],
        state="extracted",
        needs_confirmation=True,
    )
    decide(ws, job, device.id, "accept", device.revision, "user")
    run_visit(ws, job)
    preserved = next(field for field in fields(ws, job) if field.key == device.key)
    assert preserved.value == "Synthetic meter"
    assert preserved.revision == device.revision + 1
    assert preserved.review == "accepted"
