"""JSON diagnostics for an installed Ema bundle."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import keyring
from keyring.backends import fail, macOS
from keyring.backends.Windows import WinVaultKeyring

from ema import __version__
from ema.core import pdf
from ema.core.config import load_settings, workspace_path
from ema.core.resources import resource_path
from ema.core.workspace import Workspace

if sys.platform == "win32":
    from ema.windows.shell import webview2_version

RESOURCE_FILES = (
    ("audit", "measurement_norms.json"),
    ("audit", "measurement_phrases.json"),
    ("audit", "prompts", "fill_v1.txt"),
    ("audit", "prompts", "style_guide_v1.json"),
    ("consumption_analysis", "phrases.jsonl"),
    ("consumption_analysis", "trend_rules.json"),
    ("llm", "models.toml"),
    ("selfcheck", "ocr-ro.pdf"),
    ("frontend", "index.html"),
)


def check_install() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, required: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "required": required, "detail": detail})

    missing = [
        str(resource_path(*parts))
        for parts in RESOURCE_FILES
        if not resource_path(*parts).is_file()
    ]
    add("resources", not missing, True, ", ".join(missing) if missing else "present")

    ws: Workspace | None = None
    try:
        ws = Workspace(workspace_path())
        executable_dir = Path(sys.executable).resolve().parent
        outside_bundle = not (
            getattr(sys, "frozen", False) and ws.root.is_relative_to(executable_dir)
        )
        add("workspace", outside_bundle, True, str(ws.root))
    except Exception as exc:
        add("workspace", False, True, str(exc))

    try:
        settings = load_settings(ws) if ws is not None else None
    except Exception as exc:
        settings = None
        settings_error = str(exc)
    else:
        settings_error = "workspace unavailable"
    if sys.platform in {"win32", "darwin"}:
        try:
            assert settings is not None
            pages = pdf.ocr(resource_path("selfcheck", "ocr-ro.pdf"), settings)
            text = "\n".join(page.text for page in pages)
            ok = "energie" in text.casefold() and "electrică" in text.casefold()
            add("ocr", ok, True, "Romanian text recognized" if ok else "Romanian text missing")
        except Exception as exc:
            add("ocr", False, True, str(exc))
    else:
        add("ocr", True, False, "not required on this platform")

    if sys.platform == "win32":
        version = webview2_version()
        add(
            "webview2",
            version is not None,
            True,
            version or "Microsoft Edge WebView2 Runtime missing",
        )
    else:
        add("webview2", True, False, "not required on this platform")

    backend = keyring.get_keyring()
    expected = {"win32": WinVaultKeyring, "darwin": macOS.Keyring}.get(sys.platform, fail.Keyring)
    add(
        "keyring",
        isinstance(backend, expected),
        sys.platform in {"win32", "darwin"},
        backend.__class__.__name__,
    )

    if settings is not None:
        add("word", settings.word_path.exists(), False, str(settings.word_path))
    else:
        add("word", False, False, settings_error)
    return {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)), "checks": checks}
