"""S19 publication regressions: stale composition cannot become a fresh section or render."""

import pytest
from PIL import Image
from tests.unit.audit.render_seams import run_render, synthetic_render
from tests.unit.audit.test_measures import _job

from ema.audit import chapter_five, measures, render, render_writers
from ema.audit.catalogue import MaterialKind
from ema.audit.render_plan import unit_plan
from ema.audit.render_report import render_current
from ema.audit.sections import (
    Status,
    get_status,
    recompute_ready,
    record_material,
    refresh_staleness,
    set_status,
)
from ema.audit.visit import run_visit
from ema.clients.registry import get_client, update_client
from ema.core.jobs import cancel, run_stage, status, subscribe
from ema.core.review import decide, propose
from ema.core.review.models import FieldSpec


def _reading(ws, job, tmp_path):
    image = tmp_path / "screen.png"
    Image.new("RGB", (12, 8), "white").save(image)
    sha = ws.add_file("synthetic", image)
    ws.set_slot(job, "visit/meter/Panel 1/screen.png", sha)
    run_visit(ws, job)
    reading = propose(
        ws,
        job,
        FieldSpec(
            key=f"meter.panel-1.{sha[:8]}.voltage_ln.l1", label="U1", value_type="number", unit="V"
        ),
        "230",
        [],
        state="extracted",
    )
    return decide(ws, job, reading.id, "accept", reading.revision, "user").after


@pytest.mark.parametrize("change", ["correct", "cancel"])
def test_edit_between_composition_and_publication_cannot_render_stale_plan(
    tmp_path, monkeypatch, change
):
    actual_ready_runs = render_writers.ready_runs
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    reading = _reading(ws, job, tmp_path)
    original = chapter_five._plan

    def change_after_plan(view, facts):
        plan = original(view, facts)
        if change == "correct":
            decide(ws, job, reading.id, "correct", reading.revision, "user", value="231")
        else:
            cancel(ws, job)
        return plan

    monkeypatch.setattr(chapter_five, "_plan", change_after_plan)
    run = chapter_five.start_measurements(ws, job)
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    assert record["publication"] == ("stale" if change == "correct" else None)
    assert get_status(ws, job, "ch5.electric_fisa").status != Status.DRAFTED
    if change == "correct":
        with ws.connect() as db:
            folder = ws.artifact_dir(db, job, "measurements", run)
        assert '"value": "230"' in (folder / "sections/ch5.json").read_text(encoding="utf-8")
        monkeypatch.setattr(render, "ready_runs", actual_ready_runs)
        refused = run_render(ws, job)
        assert refused["state"] == "failed"
        assert refused["error"] == "measurements"
        with ws.connect() as db:
            assert (
                '"code": "output_stale"'
                in db.execute(
                    "SELECT payload FROM job_events WHERE run_id=? AND type='stage_failed'",
                    (refused["id"],),
                ).fetchone()[0]
            )
        with ws.connect() as db:
            assert (
                db.execute(
                    "SELECT count(*) FROM outputs WHERE run_id=?", (refused["id"],)
                ).fetchone()[0]
                == 0
            )


def test_changed_revision_refuses_plan_even_when_publication_says_current(tmp_path, monkeypatch):
    actual_ready_runs = render_writers.ready_runs
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    reading = _reading(ws, job, tmp_path)
    measured = chapter_five.run_measurements(ws, job)
    decide(ws, job, reading.id, "correct", reading.revision, "user", value="231")
    monkeypatch.setattr(render, "ready_runs", actual_ready_runs)
    assert run_render(ws, job)["state"] == "failed"
    with ws.connect() as db:
        assert (
            db.execute("SELECT publication FROM runs WHERE id=?", (measured.run,)).fetchone()[0]
            == "current"
        )


def test_render_inherits_measurement_reads_and_stales_on_edit_during_render(tmp_path, monkeypatch):
    actual_ready_runs = render_writers.ready_runs
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    reading = _reading(ws, job, tmp_path)
    chapter_five.run_measurements(ws, job)
    monkeypatch.setattr(render, "ready_runs", actual_ready_runs)
    writer = render.write_five

    def edit(*args, **kwargs):
        writer(*args, **kwargs)
        decide(ws, job, reading.id, "correct", reading.revision, "user", value="231")

    monkeypatch.setattr(render, "write_five", edit)
    record = run_render(ws, job)
    assert record["state"] == "ready" and record["publication"] == "stale"
    with ws.connect() as db:
        reads = db.execute(
            "SELECT table_name,row_id FROM run_reads WHERE run_id=?", (record["id"],)
        ).fetchall()
    assert ("fields", reading.id) in [tuple(row) for row in reads]


@pytest.mark.parametrize("during", [False, True])
def test_registry_fallback_rename_stales_real_unit_plan_and_sections(tmp_path, monkeypatch, during):
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    with ws.connect() as db:
        db.execute("UPDATE clients SET name='Atelier Exemplu' WHERE id='synthetic'")
    monkeypatch.setattr(render, "unit_plan", unit_plan)
    recompute_ready(ws, job)
    client = get_client(ws, "synthetic")
    build = render.build_base
    names = []

    def rename():
        update_client(ws, "synthetic", {"name": "Atelier Renumit"}, client["revision"])

    def capture(plan, **kwargs):
        names.append(plan.client_name)
        if during:
            rename()
        return build(plan, **kwargs)

    monkeypatch.setattr(render, "build_base", capture)
    record = run_render(ws, job)
    assert names == ["Atelier Exemplu"]
    assert record["state"] == "ready", record["error"]
    assert record["publication"] == ("stale" if during else "current")
    if not during:
        state = get_status(ws, job, "ch1")
        assert f"client:synthetic@{client['revision']}" in state.fingerprint
        rename()
        refresh_staleness(ws, job)
        assert get_status(ws, job, "ch1").stale
    else:
        assert get_status(ws, job, "ch1").status == Status.READY
    with ws.connect() as db:
        assert not render_current(ws, db, job, "audit_render", str(record["id"]))
        assert (
            db.execute(
                "SELECT revision FROM run_reads WHERE run_id=? "
                "AND table_name='clients' AND row_id='synthetic'",
                (record["id"],),
            ).fetchone()[0]
            == client["revision"]
        )


def test_confirming_section_does_not_invalidate_its_composition_plan(tmp_path, monkeypatch):
    actual_ready_runs = render_writers.ready_runs
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    _reading(ws, job, tmp_path)
    measured = chapter_five.run_measurements(ws, job)
    set_status(ws, job, "ch5.electric_fisa", Status.DONE, "user")
    monkeypatch.setattr(render, "ready_runs", actual_ready_runs)
    assert run_render(ws, job)["state"] == "ready"
    with ws.connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM run_reads WHERE run_id=? AND table_name='section_states'",
                (measured.run,),
            ).fetchone()[0]
            == 0
        )


def test_company_inserted_after_measures_snapshot_cannot_publish(tmp_path, monkeypatch):
    ws, job = _job(tmp_path, [[1, "Lighting", "Less use", "Energie electrică", 1, "MWh", 2, 1]])
    original = measures.ChapterSixPlan

    def insert_after_plan(**kwargs):
        plan = original(**kwargs)
        propose(ws, job, "audit.company_name", "Atelier Exemplu", [], state="supplied")
        return plan

    monkeypatch.setattr(measures, "ChapterSixPlan", insert_after_plan)
    run = run_stage(ws, job, "measures", measures.compose_measures)
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    assert record["publication"] == "stale"
    assert get_status(ws, job, "ch6.measure").status != Status.DRAFTED
    with ws.connect() as db:
        path = ws.artifact_dir(db, job, "measures", run) / "sections/ch6.json"
    assert '"company_name": null' in path.read_text(encoding="utf-8")


def test_unrelated_material_does_not_invalidate_composition(tmp_path, monkeypatch):
    ws, job, _ = synthetic_render(tmp_path, monkeypatch)
    _reading(ws, job, tmp_path)
    chapter_five.run_measurements(ws, job)
    record_material(ws, job, MaterialKind.MEASURES, True, "synthetic form")
    assert render_writers.ready_runs(ws, job, "measurements")
