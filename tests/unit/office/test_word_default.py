"""Windows Word discovery order and override paths."""

from pathlib import Path

import pytest

from ema.core.config import Settings, _word_default


def test_windows_word_default_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = tmp_path / "programs"
    second = tmp_path / "programs86"
    monkeypatch.setattr("ema.core.config.sys.platform", "win32")
    monkeypatch.setenv("PROGRAMFILES", str(first))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(second))
    candidates = [
        first / "Microsoft Office/root/Office16/WINWORD.EXE",
        second / "Microsoft Office/root/Office16/WINWORD.EXE",
        first / "Microsoft Office/Office16/WINWORD.EXE",
        second / "Microsoft Office/Office16/WINWORD.EXE",
    ]
    assert _word_default() == candidates[0]
    for candidate in reversed(candidates):
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.touch()
        assert _word_default() == candidate
    monkeypatch.setenv("EMA_WORD_PATH", str(tmp_path / "manual.exe"))
    assert Settings().word_path == tmp_path / "manual.exe"
