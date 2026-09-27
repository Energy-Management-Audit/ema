"""The built app is served under /app for deep-link reloads, without a session (D2.4)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ema import api, cli
from ema.api import create_app
from ema.core.workspace import Workspace

BASE = "http://127.0.0.1:8766"


def test_app_paths_serve_the_shell_without_a_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build = tmp_path / "frontend"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    monkeypatch.setattr(api, "resource_path", lambda *_parts: build)
    client = TestClient(create_app(Workspace(tmp_path / "ws"), 8766), base_url=BASE)
    for path in ("/app", "/app/", "/app/piee/x/date", "/app/piee/x/masuri?camp=f"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith("text/html")
        assert "id=root" in response.text
    jobs = client.get("/jobs")
    assert jobs.status_code == 403
    assert jobs.json()["type"] == "urn:ema:error:session_required"
    assert "/app/{path}" not in client.get("/openapi.json").json()["paths"]


def test_serve_prints_the_app_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EMA_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(cli.uvicorn, "Server", lambda _config: SimpleNamespace(run=lambda: None))
    result = CliRunner().invoke(cli._app, ["serve", "--port", "8766"])
    assert result.exit_code == 0, result.output
    assert "Open http://127.0.0.1:8766/app/#code=" in result.output
