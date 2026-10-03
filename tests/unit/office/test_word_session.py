"""Mac Word session ownership without launching Word."""

from pathlib import Path

import pytest

from ema.core.office.word import OsaResult, WordMac
from ema.core.office.word_api import word_session


def adapter(tmp_path: Path, *, running: bool, documents: int = 0):
    state = {"running": running, "documents": documents, "scripts": [], "forced": 0}

    def probe() -> bool:
        return bool(state["running"])

    def runner(script: str, _timeout: float) -> OsaResult:
        state["scripts"].append(script)
        if "count of documents" in script:
            return OsaResult(0, str(state["documents"]), "")
        if "quit saving no" in script:
            state["running"] = False
        return OsaResult(0, "", "")

    word = WordMac(app=tmp_path, runner=runner, process_probe=probe)

    def force_quit() -> None:
        state["forced"] += 1
        state["running"] = False

    word._force_quit = force_quit  # type: ignore[method-assign]
    return word, state


def test_quits_only_word_started_during_session(tmp_path: Path) -> None:
    word, state = adapter(tmp_path, running=False)
    with word_session(word):
        state["running"] = True
    assert state["scripts"] == [
        'tell application "Microsoft Word" to count of documents',
        'tell application "Microsoft Word" to quit saving no',
    ]
    assert state["forced"] == 0


def test_leaves_existing_word_alone(tmp_path: Path) -> None:
    word, state = adapter(tmp_path, running=True)
    with word_session(word):
        pass
    assert state["scripts"] == []


def test_leaves_open_documents_alone(tmp_path: Path) -> None:
    word, state = adapter(tmp_path, running=False, documents=1)
    with word_session(word):
        state["running"] = True
    assert len(state["scripts"]) == 1
    assert state["running"]


def test_force_quits_after_grace_period(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    word, state = adapter(tmp_path, running=False)
    ticks = iter([0.0, 10.0])
    monkeypatch.setattr("ema.core.office.word.time.monotonic", lambda: next(ticks))

    def runner(script: str, _timeout: float) -> OsaResult:
        state["scripts"].append(script)
        return OsaResult(0, "0", "")

    word.runner = runner
    with word_session(word):
        state["running"] = True
    assert state["forced"] == 1


def test_failed_graceful_quit_still_force_quits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    word, state = adapter(tmp_path, running=False)
    ticks = iter([0.0, 10.0])
    monkeypatch.setattr("ema.core.office.word.time.monotonic", lambda: next(ticks))

    def runner(script: str, _timeout: float) -> OsaResult:
        state["scripts"].append(script)
        if "count of documents" in script:
            return OsaResult(0, "0", "")
        return OsaResult(1, "", "Word did not quit")

    word.runner = runner
    with word_session(word):
        state["running"] = True
    assert state["forced"] == 1


def test_nested_sessions_quit_once_at_outer_exit(tmp_path: Path) -> None:
    word, state = adapter(tmp_path, running=False)
    with word_session(word):
        state["running"] = True
        with word_session(word):
            pass
        assert state["scripts"] == []
    assert len(state["scripts"]) == 2
