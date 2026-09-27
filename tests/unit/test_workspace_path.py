import json
from pathlib import Path

import platformdirs
import pytest
from platformdirs import windows
from platformdirs.windows import Windows

from ema.core import config


def test_windows_workspace_and_config_do_not_repeat_app_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    appdata = tmp_path / "Roaming"
    local = tmp_path / "Local"
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setattr(
        windows,
        "get_win_folder",
        lambda name: str(appdata if name == "CSIDL_APPDATA" else local),
    )
    monkeypatch.delenv("EMA_WORKSPACE", raising=False)
    monkeypatch.setattr(platformdirs, "PlatformDirs", Windows)
    monkeypatch.setattr(config.sys, "platform", "win32")

    assert config.workspace_path() == appdata / "Ema"
    (local / "Ema").mkdir(parents=True)
    (local / "Ema" / "config.toml").write_text(
        f"workspace = {json.dumps(str(tmp_path / 'custom'))}\n"
    )
    assert config.workspace_path() == tmp_path / "custom"
