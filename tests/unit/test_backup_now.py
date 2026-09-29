"""Backup reminder configuration and one-click snapshot on synthetic workspaces."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.workspace_jobs import create_job

from ema.core.backup import backup_now, restore
from ema.core.errors import EmaError
from ema.core.settings import read, settings_values, update, write_settings_values
from ema.core.workspace import Workspace


@pytest.mark.parametrize("name", ["relative", "workspace", "file"])
def test_backup_directory_validation(tmp_path: Path, name: str) -> None:
    ws = Workspace(tmp_path / "workspace")
    file = tmp_path / "file"
    file.write_text("synthetic", encoding="utf-8")
    destination = {"relative": "relative", "workspace": str(ws.root / "inside"), "file": str(file)}[
        name
    ]
    with pytest.raises(EmaError) as error:
        update(ws, {"backup_dir": destination})
    assert error.value.code == "backup_dir_invalid"


def test_backup_now_is_restorable_and_tracks_due(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    assert read(ws)["backup"]["due"] is False
    with pytest.raises(EmaError) as error:
        backup_now(ws)
    assert error.value.code == "backup_dir_missing"
    create_job(ws, "audit", "synthetic", 2026)
    assert read(ws)["backup"]["due"] is True
    update(ws, {"backup_dir": str(tmp_path / "backups")})
    (tmp_path / "backups").rmdir()
    result = backup_now(ws)
    assert (tmp_path / "backups").is_dir()
    assert result["name"].startswith("ema-backup-")
    assert Path(result["path"]).stat().st_size == result["size_bytes"]
    assert restore(Path(result["path"]), tmp_path / "restored") == tmp_path / "restored"
    state = read(ws)["backup"]
    assert state["last_name"] == result["name"]
    assert state["due"] is False
    values = settings_values(ws)
    values["last_backup_at"] = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    write_settings_values(ws, values)
    assert read(ws)["backup"]["due"] is True


def test_malformed_backup_timestamp_is_a_settings_problem(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    write_settings_values(ws, {"last_backup_at": "not-a-date"})
    with pytest.raises(EmaError) as error:
        read(ws)
    assert error.value.code == "settings_invalid"


def test_backup_directory_rejects_case_folded_workspace_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    original = os.path.normcase
    monkeypatch.setattr("ema.core.settings.os.path.normcase", lambda value: original(value).lower())
    with pytest.raises(EmaError) as error:
        update(ws, {"backup_dir": str(tmp_path / "WORKSPACE" / "inside")})
    assert error.value.code == "backup_dir_invalid"


def test_backup_write_failure_is_424(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = Workspace(tmp_path / "workspace")
    update(ws, {"backup_dir": str(tmp_path / "backups")})
    monkeypatch.setattr(
        "ema.core.backup.backup", lambda *_args: (_ for _ in ()).throw(PermissionError())
    )
    with pytest.raises(EmaError) as error:
        backup_now(ws)
    assert error.value.code == "backup_failed"
