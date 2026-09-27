"""The complete synthetic meter-photo journey stays reviewable before rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.unit.audit.test_chapter_five_render import _base, _model
from tests.unit.audit.test_readings import _record
from typer.testing import CliRunner

from ema.api import create_app
from ema.audit.chapter_five import chapter_five_plan, run_measurements
from ema.audit.chapter_five_render import render_chapter_five
from ema.audit.prompts import (
    METER_PROMPT,
    METER_PROMPT_VERSION,
    THERMAL_PROMPT,
    THERMAL_PROMPT_VERSION,
)
from ema.audit.readings import run_readings
from ema.audit.readings_schema import MeterReadout, ThermalReadout
from ema.audit.visit import run_visit
from ema.cli import _app
from ema.core.errors import EmaError
from ema.core.jobs import create_job, get_job
from ema.core.review import accept_batch, decide, fields, mark_absent
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace


def test_two_panels_confirmation_and_render(  # noqa: PLR0915
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    responses: list[dict[str, object]] = []
    images: dict[str, Path] = {}
    for panel_index, panel in enumerate(("Panel 1", "Panel 2"), 1):
        for number in (1, 2):
            name = f"display{number}.png"
            photo = tmp_path / f"{panel.replace(' ', '-')}-{name}"
            Image.new("RGB", (40, 30), (panel_index * 60, number * 60, 0)).save(photo)
            slot = f"visit/meter/{panel}/{name}"
            sha = ws.add_file("synthetic", photo)
            ws.set_slot(job, slot, sha)
            images[slot] = photo
            value = "260,00" if (panel, number) == ("Panel 2", 2) else "230,00"
            responses.append(
                _record(
                    METER_PROMPT,
                    METER_PROMPT_VERSION,
                    f"Panel: {panel}\nPhoto: {name}",
                    sha,
                    MeterReadout,
                    {
                        "readable": True,
                        "display": "voltage_ln",
                        "device": "Synthetic meter",
                        "values": [
                            {
                                "quantity": "voltage_ln",
                                "phase": "l1",
                                "value": value,
                                "unit": "V",
                                "region": [0.2, 0.2, 0.8, 0.8],
                            }
                        ],
                        "unreadable_reason": None,
                    },
                )
            )
    thermal = tmp_path / "thermal.png"
    Image.new("RGB", (40, 30), "black").save(thermal)
    thermal_sha = ws.add_file("synthetic", thermal)
    thermal_slot = "visit/thermal/thermal.png"
    ws.set_slot(job, thermal_slot, thermal_sha)
    images[thermal_slot] = thermal
    responses.append(
        _record(
            THERMAL_PROMPT,
            THERMAL_PROMPT_VERSION,
            "Photo: thermal.png",
            thermal_sha,
            ThermalReadout,
            {
                "readable": True,
                "component": "tablou",
                "spot": "30,5",
                "max": "31",
                "min": "29",
                "unreadable_reason": None,
            },
        )
    )
    recording = tmp_path / "recording.json"
    recording.write_text(
        json.dumps(
            {"source": "hand-authored", "format": "gemini-generate-content", "responses": responses}
        ),
        encoding="utf-8",
    )
    assert run_visit(ws, job).meter_photos == 4
    monkeypatch.setenv("EMA_WORKSPACE", str(ws.root))
    cli_visit = CliRunner().invoke(_app, ["audit", "visit", job])
    assert cli_visit.exit_code == 0
    assert json.loads(cli_visit.stdout)["meter_photos"] == 4
    assert run_readings(ws, job, recording=recording).photos_read == 5
    client = TestClient(
        create_app(ws, 8766, launch_code="synthetic-code"), base_url="http://127.0.0.1:8766"
    )
    csrf = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    headers = {"X-Ema-CSRF": csrf}
    visit_response = client.get(f"/jobs/{job}/visit")
    assert visit_response.status_code == 200
    assert len(visit_response.json()["panels"]) == 2
    no_live = client.post(
        f"/jobs/{job}/stages/readings",
        json={"on_revision": get_job(ws, job)["revision"]},
        headers=headers,
    )
    assert (
        no_live.status_code == 403
        and no_live.json()["title"] == "Citirea fotografiilor aşteaptă aprobarea."
    )
    pending = fields(ws, job, status="needs_confirmation")
    assert len(pending) >= 8
    filtered = client.get(f"/jobs/{job}/fields?status=needs_confirmation")
    assert filtered.status_code == 200 and len(filtered.json()) == len(pending)
    evidence_id = next(field.evidence[0] for field in pending if field.evidence)
    assert (
        client.get(f"/evidence/{evidence_id}/snippet.png?highlight=1").headers["content-type"]
        == "image/png"
    )
    assert client.get(f"/evidence/{evidence_id}/page.png").headers["content-type"] == "image/png"
    with pytest.raises(EmaError) as batch:
        accept_batch(ws, job, [(field.id, field.revision) for field in pending], "user")
    assert batch.value.code == "confirmation_individual"
    refused = client.post(
        f"/jobs/{job}/fields/accept-batch",
        json={"fields": [[pending[0].id, pending[0].revision]]},
        headers=headers,
    )
    assert refused.status_code == 409
    with pytest.raises(EmaError) as agent:
        decide(ws, job, pending[0].id, "accept", pending[0].revision, "agent")
    assert agent.value.code == "human_required"
    last = next(
        field
        for field in pending
        if field.key.endswith("voltage_ln.l1")
        and "panel-2" in field.key
        and "260" in str(field.value)
    )
    for field in pending:
        if field.id != last.id:
            if field.id == pending[0].id:
                response = client.post(
                    f"/jobs/{job}/fields/{field.id}/decide",
                    json={"action": "accept", "on_revision": field.revision},
                    headers=headers,
                )
                assert response.status_code == 200
            else:
                decide(ws, job, field.id, "accept", field.revision, "user")
    assert [field.id for field in fields(ws, job, status="needs_confirmation")] == [last.id]
    decide(ws, job, last.id, "correct", last.revision, "user", value="260.00")
    narrative_key = f"narrative.ch5.panel-2.{last.key.split('.')[2]}"
    narrative = mark_absent(
        ws,
        job,
        FieldSpec(key=narrative_key, label="Interpretarea", value_type="text", chapter="ch5"),
        "not_found",
    )
    decide(
        ws,
        job,
        narrative.id,
        "correct",
        narrative.revision,
        "user",
        value="Interpretare sintetică verificată.",
    )
    result = run_measurements(ws, job)
    assert result.figures == 5 and result.pending == 0
    assert result.plan_path.is_file()

    base, model, output = (tmp_path / name for name in ("base.docx", "model.docx", "out.docx"))
    _base(base)
    _model(model, next(iter(images.values())))
    monkeypatch.setenv("EMA_AUDIT_MEASUREMENT_SHEET_MODEL", str(model))
    monkeypatch.setenv("EMA_AUDIT_MEASUREMENT_PROTOTYPE", str(base))
    plan = chapter_five_plan(ws, job)
    report = render_chapter_five(base, output, plan, images, ("Forbidden Client",))
    assert not report.issues
    assert len(report.numbers) == 5
    assert output.is_file()
