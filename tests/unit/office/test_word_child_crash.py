"""Crash cleanup stops only the recorded private process."""

from pathlib import Path

import psutil
import pytest
from tests.unit.office.test_word_child import _bystander, _child, _source

from ema.core.office.errors import OfficeError


def test_crashed_worker_kills_recorded_word_and_spares_bystander(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMA_FAKE_WORD_MODE", "crash_word")
    bystander = _bystander()
    try:
        word = _child(tmp_path)
        with pytest.raises(OfficeError) as error:
            word.open_check(_source(tmp_path))
        assert error.value.code == "word_automation"
        assert bystander.poll() is None
        pids = [
            int(value)
            for value in (word.scratch_root / ".word_pids").read_text(encoding="utf-8").splitlines()
        ]
        assert len(pids) == 1
        assert all(
            not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
            for pid in pids
        )
        assert not list(word.scratch_root.glob("*/word.json"))
    finally:
        bystander.kill()
        bystander.wait()
