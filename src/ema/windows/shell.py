"""Small Windows shell checks used before the desktop window starts."""

import ctypes
import sys

if sys.platform == "win32":
    import winreg

WEBVIEW2_MINIMUM = (86, 0, 622, 0)
WEBVIEW2_KEY = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
_mutex_handles: list[int] = []


def _version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        return ()


def webview2_version() -> str | None:
    if sys.platform != "win32":
        return None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(root, WEBVIEW2_KEY, 0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, "pv")
            except OSError:
                continue
            if isinstance(value, str) and _version_tuple(value) >= WEBVIEW2_MINIMUM:
                return value
    return None


def single_instance(name: str) -> bool:
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, True, name)
    if not handle:
        raise ctypes.WinError()
    if kernel32.GetLastError() == 183:
        kernel32.CloseHandle(handle)
        return False
    _mutex_handles.append(handle)
    return True


def message_box(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, "Ema", 0x10)
