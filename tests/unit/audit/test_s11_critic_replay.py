"""Regression case: replay must bind a response to its request."""

import json
from pathlib import Path

import pytest

from ema.core.errors import EmaError
from ema.core.llm.replay import ReplayProvider


def test_replay_rejects_a_different_request(tmp_path: Path) -> None:
    recording = tmp_path / "exchange.json"
    recording.write_text(
        json.dumps(
            {
                "source": "hand-authored",
                "format": "openai-chat-completions",
                "responses": [
                    {
                        "choices": [{"message": {"content": "classified"}}],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    replay = ReplayProvider(recording)
    with pytest.raises(EmaError, match="request"):
        replay.respond("wrong-model", [{"role": "user", "content": "unrelated dossier"}], ())
