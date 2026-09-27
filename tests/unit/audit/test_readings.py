"""Synthetic photo replay creates reviewable, photo-backed readings."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from ema.audit.prompts import (
    METER_PROMPT,
    METER_PROMPT_VERSION,
    THERMAL_PROMPT,
    THERMAL_PROMPT_VERSION,
)
from ema.audit.readings import REPLAY_MODEL, _image, run_readings
from ema.audit.readings_schema import MeterReadout, ThermalReadout
from ema.audit.visit import VisitPhoto, run_visit
from ema.core.errors import EmaError
from ema.core.jobs import create_job
from ema.core.llm.replay import request_hashes
from ema.core.review import decide, fields
from ema.core.review.evidence import get_evidence
from ema.core.workspace import Workspace


def _record(
    prompt: str,
    version: str,
    content: str,
    sha: str,
    schema: type[MeterReadout] | type[ThermalReadout],
    answer: dict[str, object],
) -> dict[str, object]:
    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": content,
            "images": [{"sha256": sha, "media_type": "image/png"}],
        },
    ]
    return {
        "request_hashes": request_hashes(
            REPLAY_MODEL, messages, (), schema.model_json_schema(), 4096, version
        ),
        "candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }


def test_no_recording_refuses_before_any_call_and_replay_reads_each_photo(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    photo = tmp_path / "display.png"
    thermal = tmp_path / "thermal.png"
    Image.new("RGB", (40, 30), "white").save(photo)
    Image.new("RGB", (40, 30), "black").save(thermal)
    meter_sha = ws.add_file("synthetic", photo)
    thermal_sha = ws.add_file("synthetic", thermal)
    ws.set_slot(job, "visit/meter/Panel 1/display.png", meter_sha)
    ws.set_slot(job, "visit/thermal/thermal.png", thermal_sha)
    run_visit(ws, job)
    with pytest.raises(EmaError) as caught:
        run_readings(ws, job, recording=None)
    assert caught.value.code == "ai_client_disabled"
    with ws.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM llm_calls WHERE job_id=?", (job,)).fetchone()[0] == 0
        )

    meter_answer: dict[str, object] = {
        "readable": True,
        "display": "voltage_ln",
        "device": "Synthetic meter",
        "values": [
            {
                "quantity": "voltage_ln",
                "phase": "l1",
                "value": "230,00",
                "unit": "V",
                "region": [0.2, 0.2, 0.8, 0.6],
            }
        ],
        "unreadable_reason": None,
    }
    thermal_answer: dict[str, object] = {
        "readable": True,
        "component": "tablou",
        "spot": "30,5",
        "max": "31",
        "min": "29",
        "unreadable_reason": None,
    }
    recording = tmp_path / "recording.json"
    recording.write_text(
        json.dumps(
            {
                "source": "hand-authored",
                "format": "gemini-generate-content",
                "responses": [
                    _record(
                        METER_PROMPT,
                        METER_PROMPT_VERSION,
                        "Panel: Panel 1\nPhoto: display.png",
                        meter_sha,
                        MeterReadout,
                        meter_answer,
                    ),
                    _record(
                        THERMAL_PROMPT,
                        THERMAL_PROMPT_VERSION,
                        "Photo: thermal.png",
                        thermal_sha,
                        ThermalReadout,
                        thermal_answer,
                    ),
                ],
            }
        ),
        encoding="utf-8",
    )
    result = run_readings(ws, job, recording=recording)
    assert (result.photos_read, result.photos_failed, result.readings) == (2, 0, 4)
    reading = next(field for field in fields(ws, job) if field.key.endswith("voltage_ln.l1"))
    assert str(reading.value) == "230.00" and reading.needs_confirmation
    evidence = get_evidence(ws, reading.evidence[0])
    assert evidence.file_sha == meter_sha
    assert evidence.method == "vision"
    assert evidence.locator.region == (0.2, 0.2, 0.8, 0.6)


def test_photo_media_type_comes_from_bytes(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    photo = tmp_path / "display.jpg"
    Image.new("RGB", (8, 8)).save(photo, format="PNG")
    sha = ws.add_file("synthetic", photo)
    image = _image(
        ws, "synthetic", VisitPhoto(sha=sha, slot="visit/meter/P/display.jpg", name=photo.name)
    )
    assert image.media_type == "image/png"
    assert image.data == photo.read_bytes()


def test_unreadable_photo_keeps_code_in_field_and_detail_in_local_log(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    photo = tmp_path / "display.png"
    Image.new("RGB", (8, 8)).save(photo)
    sha = ws.add_file("synthetic", photo)
    ws.set_slot(job, "visit/meter/Panel 1/display.png", sha)
    run_visit(ws, job)
    detail = "synthetic unreadable reason"
    recording = tmp_path / "unreadable.json"
    recording.write_text(
        json.dumps(
            {
                "source": "hand-authored",
                "format": "gemini-generate-content",
                "responses": [
                    _record(
                        METER_PROMPT,
                        METER_PROMPT_VERSION,
                        "Panel: Panel 1\nPhoto: display.png",
                        sha,
                        MeterReadout,
                        {
                            "readable": False,
                            "display": None,
                            "device": None,
                            "values": [],
                            "unreadable_reason": detail,
                        },
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    assert run_readings(ws, job, recording=recording).photos_failed == 1
    failure = next(field for field in fields(ws, job) if field.key.endswith(".display"))
    assert failure.failure == "photo_unreadable"
    with ws.connect() as db:
        log = ws.job_path(db, job) / "log.jsonl"
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert any(
        event.get("event") == "photo_unreadable" and event.get("detail") == detail
        for event in events
    )


@pytest.mark.parametrize(
    ("action", "expected", "review"),
    [("accept", "Accepted meter", "accepted"), ("correct", "Corrected meter", "corrected")],
)
def test_later_photo_keeps_confirmed_panel_device(
    tmp_path: Path, action: str, expected: str, review: str
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    photos = [tmp_path / name for name in ("display1.png", "display2.png")]
    for index, photo in enumerate(photos):
        Image.new("RGB", (8, 8), "white" if index == 0 else "black").save(photo)
    shas = [ws.add_file("synthetic", photo) for photo in photos]
    ws.set_slot(job, "visit/meter/Panel 1/display1.png", shas[0])
    run_visit(ws, job)

    def response(photo: Path, sha: str, device: str) -> dict[str, object]:
        return _record(
            METER_PROMPT,
            METER_PROMPT_VERSION,
            f"Panel: Panel 1\nPhoto: {photo.name}",
            sha,
            MeterReadout,
            {
                "readable": True,
                "display": "voltage_ln",
                "device": device,
                "values": [],
                "unreadable_reason": None,
            },
        )

    first = tmp_path / "first.json"
    first.write_text(
        json.dumps(
            {
                "source": "hand-authored",
                "format": "gemini-generate-content",
                "responses": [response(photos[0], shas[0], "Accepted meter")],
            }
        ),
        encoding="utf-8",
    )
    run_readings(ws, job, recording=first)
    device = next(field for field in fields(ws, job) if field.key == "meter.panel-1.device")
    if action == "correct":
        decide(ws, job, device.id, "correct", device.revision, "user", value=expected)
    else:
        decide(ws, job, device.id, "accept", device.revision, "user")
    accepted = next(field for field in fields(ws, job) if field.id == device.id)
    ws.set_slot(job, "visit/meter/Panel 1/display2.png", shas[1])
    run_visit(ws, job)
    second = tmp_path / "second.json"
    second.write_text(
        json.dumps(
            {
                "source": "hand-authored",
                "format": "gemini-generate-content",
                "responses": [
                    response(photos[0], shas[0], "Accepted meter"),
                    response(photos[1], shas[1], "Different meter"),
                ],
            }
        ),
        encoding="utf-8",
    )
    run_readings(ws, job, recording=second)
    preserved = next(field for field in fields(ws, job) if field.id == device.id)
    assert (preserved.value, preserved.review, preserved.revision) == (
        expected,
        review,
        accepted.revision,
    )
