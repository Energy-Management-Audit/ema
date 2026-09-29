"""Golden tests read the real reference library and are skipped without it.

The library and generated artifacts stay outside git (docs/PLAN.md §5.15).
Point EMA_REFERENCE at it to run them: export EMA_REFERENCE=~/Code/projects/ema/data
EMA_ARTIFACTS overrides local artifacts (default: ~/Code/projects/ema/artifacts).
"""

from __future__ import annotations

import os
from functools import wraps
from pathlib import Path

import pytest

from ema.core.office.word import WordMac
from ema.core.office.word_child import WordChild


@pytest.fixture(autouse=True)
def no_real_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("keyring.get_password", lambda *_: None)
    monkeypatch.setattr("keyring.set_password", lambda *_: None)
    monkeypatch.setattr("keyring.delete_password", lambda *_: None)


@pytest.fixture(scope="session")
def reference_library() -> Path:
    location = os.environ.get("EMA_REFERENCE")
    if not location:
        pytest.skip("EMA_REFERENCE is not set — golden tests need the reference library")
    path = Path(location).expanduser()
    if not path.is_dir():
        pytest.skip(f"EMA_REFERENCE points at {path}, which does not exist")
    return path


def artifacts_path(*parts: str) -> Path:
    """Return a path under the local Ema artifacts directory."""
    root = Path(os.environ.get("EMA_ARTIFACTS", "~/Code/projects/ema/artifacts")).expanduser()
    return root.joinpath(*parts)


@pytest.fixture(autouse=True)
def require_word_marker(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Fail even when a workflow catches an unmarked attempt in a worker thread."""
    attempts: list[str] = []

    def guard(original):
        @wraps(original)
        def checked(*args, **kwargs):
            if request.node.get_closest_marker("golden") and not request.node.get_closest_marker(
                "word"
            ):
                attempts.append(request.node.nodeid)
                raise AssertionError("Golden reaches Word without pytest.mark.word")
            return original(*args, **kwargs)

        return checked

    monkeypatch.setattr(WordMac, "_perform", guard(WordMac._perform))
    monkeypatch.setattr(WordChild, "_perform", guard(WordChild._perform))
    yield
    if attempts:
        pytest.fail("Golden reaches Word without pytest.mark.word: " + attempts[0])
