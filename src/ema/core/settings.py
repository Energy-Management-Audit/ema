"""Safe local settings projection and bounded provider checks."""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.workspace import Workspace
from ema.core.workspace.lock import workspace_lock

_PROVIDERS = ("gemini", "openai")
_MODEL_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/models",
    "openai": "https://api.openai.com/v1/models",
}
_EXTRACTION = {"ocr": True, "flag_uncertain": True, "auto_accept_exact": False}


def _values(ws: Workspace) -> dict[str, Any]:
    content = ws.settings_text()
    return tomllib.loads(content) if content else {}


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int | float):
        return str(value)
    raise EmaError("settings_invalid", "Setările sunt invalide.", "")


def _write(ws: Workspace, values: dict[str, Any]) -> None:
    lines: list[str] = []
    for key, value in values.items():
        if not key.replace("_", "").isalnum():
            raise EmaError("settings_invalid", "Setările sunt invalide.", "")
        if isinstance(value, dict):
            continue
        lines.append(f"{key} = {_literal(value)}")
    for key, value in values.items():
        if isinstance(value, dict):
            table = cast("dict[str, Any]", value)
            lines.extend(
                [f"[{key}]", *(f"{name} = {_literal(item)}" for name, item in table.items())]
            )
    path = ws.settings_file()
    with tempfile.NamedTemporaryFile(
        dir=path.parent, mode="w", encoding="utf-8", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write("\n".join(lines) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read(ws: Workspace) -> dict[str, Any]:
    values = _values(ws)
    configured = load_settings(ws, workspace_values=values)
    verified = cast("dict[str, Any]", values.get("provider_verified", {}))
    return {
        "theme": values.get("theme", "light"),
        "default_provider": values.get("provider"),
        "providers": {
            name: {
                "present": bool(configured.provider_key(name)),
                "verified_at": verified.get(name),
            }
            for name in _PROVIDERS
        },
        "extraction": _EXTRACTION | values.get("extraction", {}),
    }


def update(ws: Workspace, patch: dict[str, Any]) -> dict[str, Any]:
    if any("key" in key.lower() for key in patch):
        raise EmaError("key_not_allowed", "Cheile furnizorilor se setează în mediu.", "")
    allowed = {"theme", "default_provider", "extraction"}
    if patch.keys() - allowed:
        raise EmaError("settings_invalid", "Setările sunt invalide.", "")
    with workspace_lock(ws.root):
        values = _values(ws)
        if "theme" in patch:
            values["theme"] = patch["theme"]
        if "default_provider" in patch:
            if patch["default_provider"] is None:
                values.pop("provider", None)
            else:
                values["provider"] = patch["default_provider"]
        if "extraction" in patch:
            values["extraction"] = _EXTRACTION | patch["extraction"]
        _write(ws, values)
    return read(ws)


def test_provider(ws: Workspace, provider: str) -> dict[str, Any]:
    if provider not in _PROVIDERS:
        raise EmaError("provider_invalid", "Furnizorul este invalid.", "")
    key = load_settings(ws).provider_key(provider)
    if key is None or not key.get_secret_value():
        return {"provider": provider, "status": "no_key"}
    try:
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            response = client.get(
                _MODEL_URLS[provider],
                headers={"Authorization": f"Bearer {key.get_secret_value()}"},
            )
        success = response.status_code == 200
    except httpx.HTTPError:
        success = False
    if not success:
        return {"provider": provider, "status": "failed"}
    verified_at = datetime.now(UTC).isoformat()
    with workspace_lock(ws.root):
        values = _values(ws)
        values["provider_verified"] = values.get("provider_verified", {}) | {provider: verified_at}
        _write(ws, values)
    return {"provider": provider, "status": "ok", "verified_at": verified_at}
