"""Platform selection for the shared Word interface."""

import sys
from pathlib import Path

import pytest

from ema.core.config import Settings
from ema.core.office.errors import OfficeError
from ema.core.office.word_api import word_automation, word_available, worker_command
from ema.core.office.word_child import WordChild


def test_platform_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "Word.app"
    directory.mkdir()
    executable = tmp_path / "WINWORD.EXE"
    executable.touch()
    monkeypatch.setattr("ema.core.office.word_api.sys.platform", "darwin")
    assert word_available(Settings(word_path=directory))
    assert type(word_automation(Settings(word_path=directory))).__name__ == "WordMac"
    assert not word_available(Settings(word_path=executable))
    monkeypatch.setattr("ema.core.office.word_api.sys.platform", "win32")
    assert word_available(Settings(word_path=executable))
    assert isinstance(word_automation(Settings(word_path=executable)), WordChild)
    assert not word_available(Settings(word_path=directory))
    monkeypatch.setattr("ema.core.office.word_api.sys.platform", "linux")
    assert not word_available(Settings(word_path=executable))
    with pytest.raises(OfficeError, match="no Word automation on linux"):
        word_automation(Settings(word_path=executable))


def test_worker_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert worker_command() == [sys.executable, "-m", "ema", "office-worker"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert worker_command() == [sys.executable, "office-worker"]
