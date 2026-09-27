"""COM worker cleanup with fake Python COM modules on macOS."""

import importlib
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest


@pytest.mark.parametrize("ok", [True, False])
def test_com_run_writes_result_and_always_quits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ok: bool
) -> None:
    events: list[object] = []
    pythoncom = ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: events.append("initialize")  # type: ignore[attr-defined]
    pythoncom.CoUninitialize = lambda: events.append("uninitialize")  # type: ignore[attr-defined]

    class App:
        def Quit(self, **kwargs: object) -> None:  # noqa: N802 - COM method name
            events.append(("quit", kwargs))

    client = ModuleType("win32com.client")
    client.DispatchEx = lambda name: (events.append(("dispatch", name)), App())[1]  # type: ignore[attr-defined]
    win32com = ModuleType("win32com")
    win32com.client = client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    module = importlib.reload(importlib.import_module("ema.windows.word_com"))
    monkeypatch.setattr(module, "identify_word", lambda *_args: os.getpid())
    monkeypatch.setattr(
        module,
        "perform",
        lambda *_args: (
            {"ok": ok, "tables": None}
            if ok
            else {"ok": False, "code": "word_automation", "detail": "COM failed"}
        ),
    )
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"action": "open", "input": "in.docx", "output": None}))
    assert module.run(request) == (0 if ok else 1)
    assert json.loads((tmp_path / "result.json").read_text())["ok"] is ok
    assert json.loads((tmp_path / "word.json").read_text())["pid"] == os.getpid()
    assert events == [
        "initialize",
        ("dispatch", "Word.Application"),
        ("quit", {"SaveChanges": 0}),
        "uninitialize",
    ]
