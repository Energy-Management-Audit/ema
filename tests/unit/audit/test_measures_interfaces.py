"""API, CLI and MCP dispatch to the same measures stage."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from mcp import ClientSession
from openpyxl import load_workbook
from tests.mcp_client import structured, with_client
from tests.workspace_jobs import create_job
from typer.testing import CliRunner

from ema.api import create_app
from ema.audit.measures_form import write_measures_form
from ema.cli import _app
from ema.cli import audit as cli_audit
from ema.core.jobs import get_job, status, subscribe
from ema.core.review import fields
from ema.core.workspace import Workspace

PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"


def _job(tmp_path: Path) -> tuple[Workspace, str]:
    form = write_measures_form(tmp_path / "form.xlsx")
    book = load_workbook(form)
    book["Măsuri propuse"].append(
        [1, "Lighting", "Less use", "Energie electrică", 100, "MWh", 40, 10, None]
    )
    book.save(form)
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    ws.set_slot(job, "measures", ws.add_file("synthetic", form))
    return ws, job


def _session(ws: Workspace) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(ws, PORT, launch_code="synthetic-code"), base_url=BASE)
    csrf = client.post("/session", json={"code": "synthetic-code"}).json()["csrf"]
    return client, {"x-ema-csrf": csrf}


def test_api_stage_and_blank_form(tmp_path: Path) -> None:
    ws, job = _job(tmp_path)
    client, headers = _session(ws)
    response_schema = client.get("/openapi.json").json()["paths"][
        "/audit/forms/masuri-propuse.xlsx"
    ]["get"]
    binary = response_schema["responses"]["200"]["content"]
    assert binary["application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"][
        "schema"
    ] == {"type": "string", "format": "binary"}
    downloaded = client.get("/audit/forms/masuri-propuse.xlsx")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-disposition"] == 'attachment; filename="Masuri propuse.xlsx"'
    assert downloaded.content[:2] == b"PK"
    revision = get_job(ws, job)["revision"]
    start = client.post(
        f"/jobs/{job}/stages/measures",
        json={"on_revision": revision},
        headers=headers,
    )
    assert start.status_code == 202
    assert start.json()["stage"] == "measures"
    for _ in subscribe(ws, job):
        pass
    assert status(ws, job).runs[-1]["state"] == "ready"
    assert {field.key: field.value for field in fields(ws, job)}[
        "audit_measure.1.payback_years"
    ] == 4


def test_api_missing_form_is_a_409(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    client, headers = _session(ws)
    response = client.post(
        f"/jobs/{job}/stages/measures",
        json={"on_revision": get_job(ws, job)["revision"]},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["type"] == "urn:ema:error:measures_form_missing"


def test_cli_and_mcp_use_case(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    ws, job = _job(tmp_path)
    monkeypatch.setattr(cli_audit, "workspace_path", lambda: ws.root)
    runner = CliRunner()
    blank = runner.invoke(_app, ["audit", "measures-form", str(tmp_path / "blank.xlsx")])
    assert blank.exit_code == 0
    assert (tmp_path / "blank.xlsx").is_file()
    called = runner.invoke(_app, ["audit", "measures", job])
    assert called.exit_code == 0, called.output
    assert json.loads(called.output)["measures"] == 1

    async def body(client: ClientSession) -> dict[str, object]:
        return structured(await client.call_tool("audit_measures", {"job": job}))

    result = with_client(ws, body)
    assert result["measures"] == 1
    assert result["factor_version"] == "2026-audit"
    assert {field.key: field.value for field in fields(ws, job)}[
        "audit_measure.1.payback_years"
    ] == 4
