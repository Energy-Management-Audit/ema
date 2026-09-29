"""Ema's local desktop window and its two file actions."""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TextIO, TypedDict

import uvicorn
import webview
from platformdirs import user_data_dir

from ema.api import create_app
from ema.cli.server import uvicorn_config
from ema.core.config import workspace_path
from ema.core.errors import EmaError
from ema.core.jobs import recover
from ema.core.jobs.outputs import get_output
from ema.core.logging import write_event
from ema.core.workspace import Workspace

if sys.platform == "win32":
    from ema.windows.shell import message_box, single_instance, webview2_version

if TYPE_CHECKING:
    from webview.window import Window

_desktop_logs: list[TextIO] = []
WEBVIEW2_MESSAGE = (
    "Ema are nevoie de Microsoft Edge WebView2 Runtime. Instalează-l de la "
    "https://developer.microsoft.com/microsoft-edge/webview2/ şi porneşte Ema din nou."
)


class DesktopSaveOk(TypedDict):
    ok: Literal[True]
    result: Literal["saved", "cancelled"]


class DesktopOpenOk(TypedDict):
    ok: Literal[True]
    result: Literal["opened"]


class DesktopError(TypedDict):
    ok: Literal[False]
    code: str
    message: str


type DesktopSaveResult = DesktopSaveOk | DesktopError
type DesktopOpenResult = DesktopOpenOk | DesktopError


def _local_data() -> Path:
    return Path(user_data_dir("Ema", appauthor=False, roaming=False))


class DesktopApi:
    def __init__(self, ws: Workspace) -> None:
        self._ws = ws
        self._window: Window | None = None

    def choose_folder(self) -> dict[str, str] | None:
        if self._window is None:
            raise RuntimeError("Desktop window is not ready")
        choice = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        folder = (choice if isinstance(choice, str) else choice[0]) if choice else None
        return {"path": folder} if folder else None

    def save_output(self, job_id: str, output_id: str) -> DesktopSaveResult:
        try:
            if self._window is None:
                raise RuntimeError("Desktop window is not ready")
            view, relative = get_output(self._ws, job_id, output_id)
            choice = self._window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename=str(view["download_name"])
            )
            if not choice:
                return {"ok": True, "result": "cancelled"}
            destination = choice if isinstance(choice, str) else choice[0]
            Path(destination).write_bytes(self._ws.path(relative).read_bytes())
            return {"ok": True, "result": "saved"}
        except EmaError as exc:
            return {"ok": False, "code": exc.code, "message": exc.user_message_ro}
        except Exception:
            logging.getLogger(__name__).exception(
                "Desktop save_output failed for %s/%s", job_id, output_id
            )
            raise

    def open_output(self, job_id: str, output_id: str) -> DesktopOpenResult:
        try:
            view, relative = get_output(self._ws, job_id, output_id)
            preview = _local_data() / "preview" / uuid.uuid4().hex
            preview.mkdir(parents=True)
            destination = preview / str(view["download_name"])
            destination.write_bytes(self._ws.path(relative).read_bytes())
            if sys.platform == "win32":
                os.startfile(destination)  # type: ignore[attr-defined]
            else:
                subprocess.run(["/usr/bin/open", str(destination)], check=True)
            return {"ok": True, "result": "opened"}
        except EmaError as exc:
            return {"ok": False, "code": exc.code, "message": exc.user_message_ro}
        except Exception:
            logging.getLogger(__name__).exception(
                "Desktop open_output failed for %s/%s", job_id, output_id
            )
            raise


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _redirect_stdio() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_path = workspace_path() / "logs" / "desktop.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("a", encoding="utf-8", buffering=1)
    _desktop_logs.append(handle)
    sys.stdout = handle
    sys.stderr = handle


def _start_failed(ws: Workspace) -> int:
    with ws.app_log() as handle:
        write_event(handle, "desktop_start_failed")
    if sys.platform == "win32":
        message_box("Ema nu a putut porni.")
    else:
        print("Ema nu a putut porni.", file=sys.stderr)
    return 1


def run_desktop() -> int:
    _redirect_stdio()
    if sys.platform == "win32":
        if not single_instance("Ema.Desktop"):
            message_box("Ema este deja deschisă.")
            return 0
        if webview2_version() is None:
            message_box(WEBVIEW2_MESSAGE)
            return 2

    ws = Workspace(workspace_path())
    recover(ws)
    port = _free_port()
    code = secrets.token_urlsafe(32)
    server = uvicorn.Server(uvicorn_config(create_app(ws, port, launch_code=code), port))
    server_thread = threading.Thread(target=server.run, name="ema-server", daemon=True)
    server_thread.start()
    deadline = time.monotonic() + 15
    while not server.started and server_thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        server_thread.join(timeout=10)
        return _start_failed(ws)

    local_data = _local_data()
    shutil.rmtree(local_data / "preview", ignore_errors=True)
    webview.settings["ALLOW_DOWNLOADS"] = False
    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    api = DesktopApi(ws)
    try:
        window = webview.create_window(  # pyright: ignore[reportUnknownMemberType]
            "Ema",
            f"http://127.0.0.1:{port}/app/#code={code}",
            js_api=api,
            width=1400,
            height=900,
            min_size=(1280, 800),
            background_color="#F6F2E8",
        )
        api._window = window  # pyright: ignore[reportPrivateUsage]
        webview.start(
            gui="edgechromium" if sys.platform == "win32" else None,
            private_mode=True,
            storage_path=str(local_data / "webview"),
            debug=False,
        )
    finally:
        server.should_exit = True
        server_thread.join(timeout=10)
    return 0
