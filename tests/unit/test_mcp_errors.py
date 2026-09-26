"""MCP errors carry only a code and the Romanian message; input files are confined to the roots."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession
from mcp.types import CallToolResult
from tests.audit_replay import audit_job_with_facts
from tests.mcp_client import imports_root, refusal, text, with_client

from ema.cli import app
from ema.core.errors import EmaError
from ema.core.workspace import Workspace
from ema.mcp.boundary import input_file
from ema.mcp.server import serve

OUTSIDE = "Fișierul este în afara directoarelor de import."


def _events(ws: Workspace) -> list[dict[str, Any]]:
    lines = (ws.root / "logs" / "ema.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _call(ws: Workspace, tool: str, arguments: dict[str, Any]) -> CallToolResult:
    async def body(client: ClientSession) -> CallToolResult:
        return await client.call_tool(tool, arguments)

    return with_client(ws, body)


def test_ema_error_returns_code_and_message_and_logs_detail(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")

    result = _call(ws, "job_status", {"job": "unknown-job"})

    assert result.isError
    assert text(result) == (
        'Error executing tool job_status: {"code": "job_missing", "message": "Lucrarea nu există."}'
    )
    events = _events(ws)
    assert {"event": "interface_error", "code": "job_missing", "detail": "unknown-job"}.items() <= (
        next(event for event in events if event["event"] == "interface_error").items()
    )
    tool = next(event for event in events if event["event"] == "mcp_tool")
    assert (tool["tool"], tool["outcome"], tool["code"]) == ("job_status", "error", "job_missing")
    assert isinstance(tool["duration_ms"], int)


def test_review_tools_report_an_unknown_job(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    decide = {"job": "unknown-job", "field_id": "f", "action": "accept", "on_revision": 1}

    for tool, arguments in (
        ("job_fields", {"job": "unknown-job"}),
        ("job_log", {"job": "unknown-job"}),
        ("job_decide", decide),
        ("job_checks", {"job": "unknown-job"}),
    ):
        assert text(_call(ws, tool, arguments)) == refusal(
            tool, "job_missing", "Lucrarea nu există."
        )


def test_unexpected_exception_is_internal_error_without_its_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_ws: Workspace) -> list[dict[str, Any]]:
        raise RuntimeError("secret-detail")

    monkeypatch.setattr("ema.mcp.server.list_jobs", broken)
    ws = Workspace(tmp_path / "ws")

    result = _call(ws, "job_list", {})

    assert text(result) == refusal("job_list", "internal_error", "Eroare internă Ema.")
    assert "secret-detail" not in result.model_dump_json()
    exception = next(event for event in _events(ws) if event["event"] == "exception")
    assert exception["error"] == "secret-detail"


def test_arguments_outside_the_schema_are_refused_by_the_sdk(tmp_path: Path) -> None:
    arguments = {"job": "j", "field_id": "f", "action": "approve", "on_revision": 1}

    result = _call(Workspace(tmp_path / "ws"), "job_decide", arguments)

    assert result.isError


def test_tool_events_never_carry_arguments(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    marker = "synthetic-argument-marker"

    _call(ws, "job_fields", {"job": marker, "status": "pending"})
    _call(ws, "piee_generate", {"client": marker, "year": 2025, "anexa": f"/{marker}.xlsx"})

    tool_events = [event for event in _events(ws) if event["event"] == "mcp_tool"]
    assert len(tool_events) == 2
    assert all(
        set(event) == {"at", "event", "tool", "outcome", "code", "duration_ms"}
        for event in tool_events
    )
    assert marker not in json.dumps(tool_events)


def test_paths_are_confined_to_the_import_roots(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    root = imports_root(ws)
    inside = root / "Anexa.xlsx"
    inside.write_bytes(b"synthetic")
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"synthetic")
    (root / "link.xlsx").symlink_to(outside)
    cases = (
        ("Anexa.xlsx", "path_outside_roots"),
        (str(outside), "path_outside_roots"),
        (str(root / "link.xlsx"), "path_outside_roots"),
        (str(root / "absent.xlsx"), "file_missing"),
        (str(root), "file_missing"),
    )

    assert input_file((root,), str(inside)) == inside
    for value, code in cases:
        with pytest.raises(EmaError) as refused:
            input_file((root,), value)
        assert refused.value.code == code, value
    result = _call(ws, "piee_generate", {"client": "c", "year": 2025, "anexa": str(outside)})
    assert text(result) == refusal("piee_generate", "path_outside_roots", OUTSIDE)
    arguments = {"job": "j", "section": "ch2.date_generale", "draft_recording": str(outside)}
    assert text(_call(ws, "audit_draft_section", arguments)) == refusal(
        "audit_draft_section", "path_outside_roots", OUTSIDE
    )


def test_unreadable_recording_is_replay_invalid_with_no_run(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = audit_job_with_facts(ws)
    root = imports_root(ws)
    (root / "not-json.json").write_text("{ not json")
    (root / "listed.json").write_text("[]")

    for name in ("not-json.json", "listed.json"):
        recording = str(root / name)
        arguments = {
            "job": job,
            "section": "ch2.date_generale",
            "draft_recording": recording,
            "support_recording": recording,
        }
        assert text(_call(ws, "audit_draft_section", arguments)) == refusal(
            "audit_draft_section", "replay_invalid", "Înregistrarea AI este invalidă."
        )
    with ws.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM runs WHERE job_id=?", (job,)).fetchone()[0] == 0


def test_missing_import_root_exits_with_its_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EMA_WORKSPACE", str(tmp_path / "ws"))
    missing = tmp_path / "missing"
    monkeypatch.setattr(sys, "argv", ["ema", "mcp", "--import-root", str(missing)])

    with pytest.raises(SystemExit) as exited:
        app()

    assert exited.value.code == 1
    assert "Directorul de import nu există." in capsys.readouterr().err


def test_serve_creates_the_imports_folder_and_logs_its_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[str] = []
    monkeypatch.setenv("EMA_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setattr(
        "mcp.server.fastmcp.FastMCP.run", lambda _self, transport: started.append(transport)
    )
    extra = tmp_path / "received"
    extra.mkdir()

    serve([extra])

    ws = Workspace(tmp_path / "ws")
    assert (ws.root / "imports").is_dir()
    assert started == ["stdio"]
    event = next(event for event in _events(ws) if event["event"] == "mcp_started")
    assert event["import_roots"] == 2
