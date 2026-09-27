"""Safe local settings projection and bounded provider checks."""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import keyring
from keyring.errors import KeyringError, PasswordDeleteError

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


def settings_values(ws: Workspace) -> dict[str, Any]:
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


def write_settings_values(ws: Workspace, values: dict[str, Any]) -> None:
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
    values = settings_values(ws)
    configured = load_settings(ws, workspace_values=values)
    verified = cast("dict[str, Any]", values.get("provider_verified", {}))
    providers: dict[str, dict[str, Any]] = {}
    for name in _PROVIDERS:
        secret = configured.provider_key(name)
        key = secret.get_secret_value() if secret else None
        source = None
        if key:
            source = "environment" if os.environ.get(f"EMA_{name.upper()}_API_KEY") else "keyring"
        providers[name] = {
            "present": bool(key),
            "verified_at": verified.get(name),
            "hint": _key_hint(key),
            "source": source,
        }
    last_at = values.get("last_backup_at")
    try:
        last_backup = datetime.fromisoformat(last_at) if isinstance(last_at, str) else None
        if last_at is not None and (last_backup is None or last_backup.tzinfo is None):
            raise ValueError("invalid backup timestamp")
    except ValueError as exc:
        raise EmaError("settings_invalid", "Setările sunt invalide.", "") from exc
    with ws.connect() as db:
        has_jobs = (
            db.execute(
                "SELECT 1 FROM jobs WHERE deleted=0 AND type!='reporting' LIMIT 1"
            ).fetchone()
            is not None
        )
    return {
        "theme": values.get("theme", "light"),
        "default_provider": values.get("provider"),
        "providers": providers,
        "extraction": _EXTRACTION | values.get("extraction", {}),
        "workspace": str(ws.root),
        "backup": {
            "dir": values.get("backup_dir"),
            "last_at": last_at,
            "last_size": values.get("last_backup_size"),
            "last_name": values.get("last_backup_name"),
            "due": has_jobs
            and (
                last_at is None
                or (
                    last_backup is not None and datetime.now(UTC) - last_backup >= timedelta(days=7)
                )
            ),
        },
    }


def _key_hint(key: str | None) -> str | None:
    if not key:
        return None
    return key[:4] + "••••••••" + key[-4:] if len(key) >= 12 else "••••••••"


def backup_folder(ws: Workspace, value: str) -> str:
    try:
        folder = Path(value).expanduser()
        if not folder.is_absolute():
            raise ValueError("relative backup directory")
        folder = folder.resolve()
        workspace = ws.root.resolve()
        folder_case = os.path.normcase(str(folder))
        workspace_case = os.path.normcase(str(workspace))
        inside = folder_case == workspace_case or folder_case.startswith(workspace_case + os.sep)
        if not inside:
            inside = any(
                ancestor.exists() and os.path.samefile(ancestor, workspace)
                for ancestor in (folder, *folder.parents)
            )
        if inside or folder.is_file():
            raise ValueError("backup inside workspace or file")
        folder.mkdir(parents=True, exist_ok=True)
    except (OSError, ValueError) as exc:
        raise EmaError(
            "backup_dir_invalid", "Dosarul pentru copii nu poate fi folosit.", ""
        ) from exc
    return str(folder)


def update(ws: Workspace, patch: dict[str, Any]) -> dict[str, Any]:
    if any("key" in key.lower() for key in patch):
        raise EmaError("key_not_allowed", "Cheile furnizorilor se setează în mediu.", "")
    allowed = {"theme", "default_provider", "extraction", "backup_dir"}
    if patch.keys() - allowed:
        raise EmaError("settings_invalid", "Setările sunt invalide.", "")
    with workspace_lock(ws.root):
        values = settings_values(ws)
        if "theme" in patch:
            values["theme"] = patch["theme"]
        if "default_provider" in patch:
            if patch["default_provider"] is None:
                values.pop("provider", None)
            else:
                values["provider"] = patch["default_provider"]
        if "extraction" in patch:
            values["extraction"] = _EXTRACTION | patch["extraction"]
        if "backup_dir" in patch:
            if patch["backup_dir"] is None:
                values.pop("backup_dir", None)
            else:
                values["backup_dir"] = backup_folder(ws, patch["backup_dir"])
        write_settings_values(ws, values)
    return read(ws)


def set_provider_key(ws: Workspace, provider: str, key: str) -> None:
    if provider not in _PROVIDERS:
        raise EmaError("provider_invalid", "Furnizorul este invalid.", "")
    try:
        keyring.set_password("Ema", f"{provider}_api_key", key)
    except (KeyringError, OSError, RuntimeError) as exc:
        raise EmaError(
            "keyring_unavailable", "Depozitul de chei al sistemului nu este disponibil.", ""
        ) from exc
    with workspace_lock(ws.root):
        values = settings_values(ws)
        verified = cast("dict[str, Any]", values.get("provider_verified", {}))
        verified.pop(provider, None)
        values["provider_verified"] = verified
        if not values.get("provider"):
            values["provider"] = provider
        write_settings_values(ws, values)


def remove_provider_key(ws: Workspace, provider: str) -> None:
    if provider not in _PROVIDERS:
        raise EmaError("provider_invalid", "Furnizorul este invalid.", "")
    with workspace_lock(ws.root):
        values = settings_values(ws)
        other = next(name for name in _PROVIDERS if name != provider)
        other_present = (
            bool(load_settings(ws, workspace_values=values).provider_key(other))
            if values.get("provider") == provider
            else False
        )
        try:
            keyring.delete_password("Ema", f"{provider}_api_key")
        except PasswordDeleteError:
            pass
        except (KeyringError, OSError, RuntimeError) as exc:
            raise EmaError(
                "keyring_unavailable", "Depozitul de chei al sistemului nu este disponibil.", ""
            ) from exc
        verified = cast("dict[str, Any]", values.get("provider_verified", {}))
        verified.pop(provider, None)
        values["provider_verified"] = verified
        if values.get("provider") == provider:
            if other_present:
                values["provider"] = other
            else:
                values.pop("provider", None)
        write_settings_values(ws, values)


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
        values = settings_values(ws)
        values["provider_verified"] = values.get("provider_verified", {}) | {provider: verified_at}
        write_settings_values(ws, values)
    return {"provider": provider, "status": "ok", "verified_at": verified_at}
