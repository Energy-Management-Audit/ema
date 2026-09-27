"""Windows shell behavior without a Windows runtime on the Mac."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from ema.windows import shell


def test_webview2_registry_checks_both_hives_and_minimum(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell.sys, "platform", "win32")
    queried: list[tuple[int, str, int]] = []
    version = "86.0.622.0"

    def open_key(root: int, path: str, _reserved: int, access: int) -> object:
        queried.append((root, path, access))
        return nullcontext(root)

    def query_value(root: int, name: str) -> tuple[str, int]:
        assert name == "pv"
        if root == 1:
            raise OSError("not installed for this user")
        return version, 1

    registry = SimpleNamespace(
        HKEY_CURRENT_USER=1,
        HKEY_LOCAL_MACHINE=2,
        KEY_WOW64_64KEY=256,
        KEY_WOW64_32KEY=512,
        KEY_READ=1,
        OpenKey=open_key,
        QueryValueEx=query_value,
    )
    monkeypatch.setattr(shell, "winreg", registry, raising=False)
    assert shell.webview2_version() == "86.0.622.0"
    assert queried[0][0] == 1 and queried[2][0] == 2
    assert all(path == shell.WEBVIEW2_KEY for _, path, _ in queried)
    version = "85.0.0.0"
    assert shell.webview2_version() is None


def test_mutex_keeps_first_handle_and_rejects_second(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell.sys, "platform", "win32")
    shell._mutex_handles.clear()
    errors = iter((0, 183))
    handles = iter((11, 12))
    closed: list[int] = []
    kernel = SimpleNamespace(
        CreateMutexW=lambda _security, _owner, _name: next(handles),
        GetLastError=lambda: next(errors),
        CloseHandle=closed.append,
    )
    monkeypatch.setattr(shell.ctypes, "windll", SimpleNamespace(kernel32=kernel), raising=False)
    assert shell.single_instance("Ema.Desktop") is True
    assert shell.single_instance("Ema.Desktop") is False
    assert shell._mutex_handles == [11]
    assert closed == [12]
    shell._mutex_handles.clear()


def test_windows_message_box_uses_ema_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell.sys, "platform", "win32")
    shown: list[tuple[object, str, str, int]] = []
    user32 = SimpleNamespace(MessageBoxW=lambda *args: shown.append(args))
    monkeypatch.setattr(shell.ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    shell.message_box("Ema este deja deschisă.")
    assert shown == [(None, "Ema este deja deschisă.", "Ema", 0x10)]
