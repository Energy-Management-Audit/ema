"""Windows-only COM glue for the supervised Word worker."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, cast

import psutil
import pythoncom
import win32com.client

from ema.core.office.word_child import identify_word
from ema.windows.word_steps import perform


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(value), encoding="utf-8")
    os.replace(pending, path)


def run(request: Path) -> int:
    folder = request.parent
    action = json.loads(request.read_text(encoding="utf-8"))["action"]
    app: Any = None
    pythoncom.CoInitialize()
    try:
        before = [
            process.pid
            for process in psutil.process_iter()
            if process.name().casefold() == "winword.exe"
        ]
        started_at = time.time()
        _atomic_json(folder / "launch.json", {"before": before, "started_at": started_at})
        app = cast(Any, win32com.client).DispatchEx("Word.Application")
        deadline = time.monotonic() + 10
        pid = None
        while pid is None and time.monotonic() < deadline:
            pid = identify_word(before, started_at)
            if pid is None:
                time.sleep(0.05)
        if pid is None:
            _atomic_json(
                folder / "result.json",
                {"ok": False, "code": "word_launch", "detail": "word process unidentified"},
            )
            return 1
        _atomic_json(
            folder / "word.json", {"pid": pid, "create_time": psutil.Process(pid).create_time()}
        )
        result = perform(app, action, folder)
        _atomic_json(folder / "result.json", result)
        return 0 if result["ok"] else 1
    finally:
        try:
            if app is not None:
                app.Quit(SaveChanges=0)
        finally:
            pythoncom.CoUninitialize()
