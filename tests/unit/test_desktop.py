"""Desktop file actions and the window lifecycle on synthetic data."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from tests.workspace_jobs import create_job

from ema.core.jobs import StageContext, StageOutcome, run_stage, subscribe
from ema.core.jobs.outputs import get_output, list_outputs
from ema.core.workspace import Workspace
from ema.windows import shell

desktop = import_module("ema.cli.desktop")


def _stage(ctx: StageContext) -> StageOutcome:
    source = ctx.artifact_dir() / "PIEE-draft.docx"
    source.write_bytes(b"PK synthetic")
    ctx.save_output(source, source.name)
    return StageOutcome()


def _output(tmp_path: Path) -> tuple[Workspace, str, str, Path]:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "piee", "synthetic", 2026)
    run_stage(ws, job, "piee_generate", _stage)
    for _ in subscribe(ws, job):
        pass
    output_id = list_outputs(ws, job)[0]["id"]
    _, relative = get_output(ws, job, output_id)
    return ws, job, output_id, ws.path(relative)


def test_bridge_saves_cancels_and_checks_output_freshness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, job, output_id, source = _output(tmp_path)
    api = desktop.DesktopApi(ws)
    destination = tmp_path / "saved.docx"
    choices = [str(destination), None]
    dialogs: list[tuple[object, str]] = []

    def choose(dialog_type: object, *, save_filename: str) -> str | None:
        dialogs.append((dialog_type, save_filename))
        return choices.pop(0)

    api._window = SimpleNamespace(create_file_dialog=choose)
    assert api.save_output(job, output_id) == {"ok": True, "result": "saved"}
    assert destination.read_bytes() == b"PK synthetic"
    assert dialogs[0][1] == "PIEE-draft.docx"
    assert api.save_output(job, output_id) == {"ok": True, "result": "cancelled"}
    assert {name for name in dir(api) if not name.startswith("_")} == {
        "open_output",
        "save_output",
        "choose_folder",
    }
    assert api.save_output(job, "missing") == {
        "ok": False,
        "code": "output_missing",
        "message": "Documentul nu există.",
    }
    assert api.open_output(job, "missing") == {
        "ok": False,
        "code": "output_missing",
        "message": "Documentul nu există.",
    }

    source.write_bytes(b"externally changed")
    assert api.save_output(job, output_id) == {
        "ok": False,
        "code": "output_stale",
        "message": "Documentul a fost modificat extern.",
    }
    assert destination.read_bytes() == b"PK synthetic"
    monkeypatch.setattr(desktop, "_local_data", lambda: tmp_path / "local")
    assert api.open_output(job, output_id) == {
        "ok": False,
        "code": "output_stale",
        "message": "Documentul a fost modificat extern.",
    }
    assert not (tmp_path / "local").exists()


def test_bridge_opens_a_private_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws, job, output_id, _ = _output(tmp_path)
    opened: list[Path] = []
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "_local_data", lambda: tmp_path / "local")
    monkeypatch.setattr(
        desktop.subprocess, "run", lambda command, **_kwargs: opened.append(Path(command[1]))
    )
    api = desktop.DesktopApi(ws)
    assert api.open_output(job, output_id) == {"ok": True, "result": "opened"}
    assert opened[0].name == "PIEE-draft.docx"
    assert opened[0].read_bytes() == b"PK synthetic"


def test_bridge_unexpected_error_raises_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    ws, job, output_id, _ = _output(tmp_path)
    api = desktop.DesktopApi(ws)
    api._window = SimpleNamespace(create_file_dialog=lambda *_args, **_kwargs: None)

    def fail(*_args: object) -> None:
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(desktop, "get_output", fail)
    with pytest.raises(OSError, match="synthetic disk failure"):
        api.save_output(job, output_id)
    with pytest.raises(OSError, match="synthetic disk failure"):
        api.open_output(job, output_id)
    assert "Desktop save_output failed" in caplog.text
    assert "Desktop open_output failed" in caplog.text


def test_window_starts_on_the_local_app_and_stops_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(desktop.sys, "platform", "darwin")

    class Server:
        started = False
        should_exit = False

        def __init__(self, config: object) -> None:
            calls["config"] = config
            calls["server"] = self

        def run(self) -> None:
            self.started = True

    def create_window(title: str, url: str, **kwargs: object) -> object:
        calls["window"] = (title, url, kwargs)
        return object()

    def start(**kwargs: object) -> None:
        calls["start"] = kwargs

    monkeypatch.setattr(desktop.uvicorn, "Server", Server)
    monkeypatch.setattr(desktop, "workspace_path", lambda: tmp_path / "workspace")
    monkeypatch.setattr(desktop, "_local_data", lambda: tmp_path / "local")
    monkeypatch.setattr(desktop, "_free_port", lambda: 8799)
    monkeypatch.setattr(desktop, "create_app", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        desktop, "webview", SimpleNamespace(settings={}, create_window=create_window, start=start)
    )
    assert desktop.run_desktop() == 0
    title, url, kwargs = calls["window"]
    assert title == "Ema"
    assert url.startswith("http://127.0.0.1:8799/app/#code=")
    assert kwargs["min_size"] == (1280, 800)
    assert kwargs["background_color"] == "#F6F2E8"
    assert calls["start"]["private_mode"] is True
    assert calls["start"]["storage_path"] == str(tmp_path / "local" / "webview")
    assert calls["server"].should_exit is True


def test_window_start_failure_is_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "darwin")

    class Server:
        started = False
        should_exit = False

        def __init__(self, _config: object) -> None:
            pass

        def run(self) -> None:
            pass

    monkeypatch.setattr(desktop.uvicorn, "Server", Server)
    monkeypatch.setattr(desktop, "workspace_path", lambda: tmp_path / "workspace")
    monkeypatch.setattr(desktop, "_free_port", lambda: 8799)
    monkeypatch.setattr(desktop, "create_app", lambda *_args, **_kwargs: object())
    assert desktop.run_desktop() == 1
    log = (tmp_path / "workspace" / "logs" / "ema.jsonl").read_text(encoding="utf-8")
    assert '"event": "desktop_start_failed"' in log


def test_windowed_executable_keeps_one_utf8_stdio_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(desktop, "workspace_path", lambda: tmp_path)
    with monkeypatch.context() as context:
        context.setattr(sys, "stdout", None)
        context.setattr(sys, "stderr", None)
        desktop._redirect_stdio()
        assert sys.stdout is sys.stderr
        print("ştiinţă")
    desktop._desktop_logs.pop().close()
    assert "ştiinţă" in (tmp_path / "logs" / "desktop.log").read_text(encoding="utf-8")


def test_non_windows_shell_functions_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell.sys, "platform", "darwin")
    assert shell.single_instance("Ema.Desktop") is True
    assert shell.webview2_version() is None
    shell.message_box("synthetic")


def test_choose_folder_returns_contract_path_or_null(tmp_path: Path) -> None:
    api = desktop.DesktopApi(Workspace(tmp_path / "workspace"))
    with pytest.raises(RuntimeError, match="window is not ready"):
        api.choose_folder()
    choices = [[str(tmp_path / "delivery")], None]
    dialogs = []

    def choose(kind):
        dialogs.append(kind)
        return choices.pop(0)

    api._window = SimpleNamespace(create_file_dialog=choose)
    assert api.choose_folder() == {"path": str(tmp_path / "delivery")}
    assert api.choose_folder() is None
    assert dialogs == [desktop.webview.FileDialog.FOLDER] * 2
