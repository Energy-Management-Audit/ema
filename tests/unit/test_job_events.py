"""Durable progress ordering, replay, and SSE polling."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.workspace_jobs import create_job

from ema.api import create_app
from ema.core.errors import EmaError
from ema.core.jobs import StageOutcome, run_stage, status, subscribe
from ema.core.jobs.events import replay
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def _client(ws: Workspace) -> TestClient:
    client = TestClient(create_app(ws, 8766, launch_code="synthetic-code"), base_url=BASE)
    assert client.post("/session", json={"code": "synthetic-code"}).status_code == 200
    return client


def test_replay_order_and_item_failure_stays_ready(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "piee", "synthetic", 2026)

    def generate(ctx):  # type: ignore[no-untyped-def]
        ctx.progress(1, 2, "Pregătire")
        ctx.progress(2, 2, "Finalizare")
        return StageOutcome(item_failures=["sensitive item value"], warnings=["warning"])

    run = run_stage(ws, job, "piee_generate", generate)
    list(subscribe(ws, job))
    assert next(item for item in status(ws, job).runs if item["id"] == run)["state"] == "ready"
    events, terminal = replay(ws, job, 0)
    assert terminal
    assert [event.type for event in events] == [
        "stage_started",
        "stage_progress",
        "stage_progress",
        "item_failed",
        "stage_finished",
    ]
    assert [event.seq for event in events] == sorted({event.seq for event in events})
    assert events[-1].payload == {
        "state": "ready",
        "publication": "current",
        "item_failures": 1,
        "warnings": 1,
    }
    client = _client(ws)
    response = client.get(f"/jobs/{job}/events", headers={"Last-Event-ID": str(events[1].seq)})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert [line for line in response.text.splitlines() if line.startswith("id: ")] == [
        f"id: {event.seq}" for event in events[2:]
    ]
    assert "sensitive item value" not in response.text
    invalid = client.get(f"/jobs/{job}/events", headers={"Last-Event-ID": "-1"})
    assert invalid.status_code == 400
    assert invalid.json()["type"] == "urn:ema:error:invalid_cursor"


def test_active_stream_keepalive_then_terminal(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ws = Workspace(tmp_path)
    job = create_job(ws, "piee", "synthetic", 2026)
    release = threading.Event()

    def generate(ctx):  # type: ignore[no-untyped-def]
        assert release.wait(5)
        ctx.progress(1, 1, "Finalizare")
        return StageOutcome()

    run_stage(ws, job, "piee_generate", generate)
    polls = 0

    async def poll() -> None:
        nonlocal polls
        polls += 1
        if polls == 16:
            release.set()
        await asyncio.sleep(0.001)

    monkeypatch.setattr("ema.api.routes._poll_events", poll)
    response = _client(ws).get(f"/jobs/{job}/events")
    assert response.status_code == 200
    assert ": keepalive\n\n" in response.text
    assert "event: stage_finished" in response.text


def test_failed_stage_hides_exception_detail_over_http(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "piee", "synthetic", 2026)

    def fail(_ctx):  # type: ignore[no-untyped-def]
        raise EmaError("synthetic_failure", "Etapa a eșuat.", "sensitive detail")

    run_stage(ws, job, "piee_generate", fail)
    list(subscribe(ws, job))
    client = _client(ws)
    response = client.get(f"/jobs/{job}/status")
    assert response.status_code == 200
    assert "sensitive detail" not in response.text
    assert response.json()["runs"][-1]["state"] == "failed"
    stream = client.get(f"/jobs/{job}/events")
    assert "event: stage_failed" in stream.text
    assert "sensitive detail" not in stream.text


def test_stage_revision_precondition_is_atomic_with_start(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    job = create_job(ws, "piee", "synthetic", 2026)
    with pytest.raises(EmaError) as stale:
        run_stage(ws, job, "piee_generate", lambda _ctx: StageOutcome(), on_revision=0)
    assert stale.value.code == "stale_revision"
    with ws.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs WHERE job_id=?", (job,)).fetchone()[0] == 0
        assert (
            db.execute("SELECT COUNT(*) FROM job_events WHERE job_id=?", (job,)).fetchone()[0] == 0
        )
