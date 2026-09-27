"""Update route session and refresh behavior."""

import json
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPException
from pathlib import Path
from threading import Event, Lock
from typing import Literal

import pytest
from fastapi.testclient import TestClient

from ema.api import create_app, update_routes
from ema.core.updates import UpdateStatus, check_update
from ema.core.workspace import Workspace


def _client(tmp_path: Path, *, mock: bool = False) -> TestClient:
    return TestClient(
        create_app(Workspace(tmp_path), 8766, launch_code="synthetic-code", mock=mock),
        base_url="http://127.0.0.1:8766",
    )


def _session(client: TestClient) -> None:
    assert client.post("/session", json={"code": "synthetic-code"}).status_code == 200


@pytest.mark.parametrize("state", ["ok", "no_release"])
def test_shape_session_and_six_hour_cache(
    tmp_path: Path, monkeypatch, state: Literal["ok", "no_release"]
) -> None:
    clock = [1000.0]
    calls: list[str] = []
    monkeypatch.setattr(update_routes.time, "monotonic", lambda: clock[0])

    def check(current: str) -> UpdateStatus:
        calls.append(current)
        return UpdateStatus(
            current,
            "0.2.0" if state == "ok" else None,
            state == "ok",
            "Notes" if state == "ok" else None,
            "https://github.com/Energy-Management-Audit/ema-releases/releases/tag/v0.2.0"
            if state == "ok"
            else None,
            None,
            "2026-09-27T08:00:00+00:00",
            state,
        )

    monkeypatch.setattr(update_routes, "check_update", check)
    client = _client(tmp_path)
    assert client.get("/settings/update").status_code == 403
    _session(client)
    first = client.get("/settings/update")
    assert first.status_code == 200
    assert set(first.json()) == {
        "current",
        "latest",
        "newer",
        "notes",
        "page_url",
        "download_url",
        "checked_at",
        "state",
    }
    clock[0] += 21599
    assert client.get("/settings/update").json() == first.json()
    assert len(calls) == 1
    clock[0] += 1
    client.get("/settings/update")
    assert len(calls) == 2


def test_unavailable_ten_minute_cache_and_mock(tmp_path: Path, monkeypatch) -> None:
    clock = [1000.0]
    calls: list[str] = []
    monkeypatch.setattr(update_routes.time, "monotonic", lambda: clock[0])

    def check(current: str) -> UpdateStatus:
        calls.append(current)
        return UpdateStatus(
            current, None, False, None, None, None, "2026-09-27T08:00:00+00:00", "unavailable"
        )

    monkeypatch.setattr(update_routes, "check_update", check)
    client = _client(tmp_path / "real")
    _session(client)
    assert client.get("/settings/update").json()["state"] == "unavailable"
    clock[0] += 599
    client.get("/settings/update")
    assert len(calls) == 1
    clock[0] += 1
    client.get("/settings/update")
    assert len(calls) == 2
    mock = _client(tmp_path / "mock", mock=True)
    _session(mock)
    assert mock.get("/settings/update").json()["state"] == "no_release"
    assert len(calls) == 2


def test_http_transport_failure_returns_unavailable_with_backoff(
    tmp_path: Path, monkeypatch
) -> None:
    clock = [1000.0]
    attempts: list[str] = []
    monkeypatch.setattr(update_routes.time, "monotonic", lambda: clock[0])

    def broken(url: str, *, allowed_host: str) -> tuple[str, str, bytes]:
        attempts.append(url)
        assert allowed_host == "api.github.com"
        raise HTTPException("synthetic truncated response")

    monkeypatch.setattr(
        update_routes, "check_update", lambda current: check_update(current, fetch=broken)
    )
    client = _client(tmp_path)
    _session(client)
    first = client.get("/settings/update")
    assert (first.status_code, first.json()["state"]) == (200, "unavailable")
    clock[0] += 599
    assert client.get("/settings/update").json() == first.json()
    assert len(attempts) == 1
    clock[0] += 1
    assert client.get("/settings/update").json()["state"] == "unavailable"
    assert len(attempts) == 2


def test_slow_update_does_not_block_other_requests(tmp_path: Path, monkeypatch) -> None:
    entered = Event()
    second_entered = Event()
    release = Event()
    calls_lock = Lock()
    calls = 0

    def slow_fetch(url: str, *, allowed_host: str) -> tuple[str, str, bytes]:
        nonlocal calls
        assert url.endswith("/releases/latest")
        assert allowed_host == "api.github.com"
        with calls_lock:
            calls += 1
            (entered if calls == 1 else second_entered).set()
        assert release.wait(15)
        body = json.dumps(
            {"tag_name": "v0.2.0", "body": "synthetic", "html_url": None, "assets": []}
        ).encode()
        return url, "application/json", body

    monkeypatch.setattr(
        update_routes,
        "check_update",
        lambda current: check_update(current, fetch=slow_fetch),
    )
    client = _client(tmp_path)
    _session(client)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(client.get, "/settings/update")
        try:
            assert entered.wait(10)
            workspace = pool.submit(client.get, "/settings")
            assert workspace.result(timeout=5).status_code == 200
            second = pool.submit(client.get, "/settings/update")
            assert second_entered.wait(10)
        finally:
            release.set()
        assert first.result(timeout=5).json()["state"] == "ok"
        assert second.result(timeout=5).json()["state"] == "ok"
    assert calls == 2
