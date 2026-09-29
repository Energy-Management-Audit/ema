"""Word goldens cannot reach the native driver without declaring the shared slot."""

from types import SimpleNamespace

import pytest
from tests.conftest import require_word_marker

from ema.core.office.word import WordMac
from ema.core.office.word_child import WordChild


@pytest.mark.parametrize("driver", [WordMac, WordChild])
@pytest.mark.parametrize("marked", [False, True])
def test_golden_word_guard_blocks_before_driver_and_checks_teardown(monkeypatch, driver, marked):
    called = []
    monkeypatch.setattr(driver, "_perform", lambda *_: called.append(True))
    request = SimpleNamespace(
        node=SimpleNamespace(
            nodeid="synthetic-golden",
            get_closest_marker=lambda name: name == "golden" or (name == "word" and marked),
        )
    )
    guard = require_word_marker.__wrapped__(request, monkeypatch)
    next(guard)
    if marked:
        driver._perform(None)
        assert called == [True]
        with pytest.raises(StopIteration):
            next(guard)
    else:
        with pytest.raises(AssertionError, match=r"without pytest\.mark\.word"):
            driver._perform(None)
        assert called == []
        with pytest.raises(pytest.fail.Exception, match="synthetic-golden"):
            next(guard)
