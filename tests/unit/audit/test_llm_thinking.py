"""Thinking tokens are recorded with the spend and replay, and a call past its cap is logged."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel
from tests.workspace_jobs import create_job

from ema.core.llm import AgentContext, ReplayProvider, complete_json
from ema.core.llm.recording import RecordingProvider
from ema.core.llm.types import Exchange
from ema.core.workspace import Workspace

CAP = 2048
MESSAGES = [{"role": "user", "content": "synthetic draft"}]


class Answer(BaseModel):
    item: int


class Thinking:
    name = "gemini"

    def __init__(self, thoughts: int) -> None:
        self.thoughts = thoughts

    def respond(self, *_args: object, **_kwargs: object) -> Exchange:
        return Exchange('{"item": 1}', (), 10, 20 + self.thoughts, thoughts_tokens=self.thoughts)


def _events(ws: Workspace, job: str) -> list[dict[str, object]]:
    with ws.connect() as db:
        log = ws.job_path(db, job) / "log.jsonl"
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return [json.loads(line) for line in lines]


@pytest.mark.parametrize(("thoughts", "logged"), [(CAP + 1, True), (CAP, False), (0, False)])
def test_thoughts_go_to_the_spend_row_and_past_the_cap_to_the_log(
    tmp_path: Path, thoughts: int, logged: bool
) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    context = AgentContext(
        ws, job, "draft:3-1", Thinking(thoughts), "gemini-3.6-flash", "v1", synthetic=True
    )
    complete_json(context, Answer, "Draft", "text", thinking_tokens=CAP)
    with ws.connect() as db:
        row = db.execute("SELECT output_tokens, thoughts_tokens FROM llm_calls").fetchone()
    assert tuple(row) == (20 + thoughts, thoughts)
    over = [event for event in _events(ws, job) if event["event"] == "ai_thinking_over_cap"]
    expected = [{"section": "draft:3-1", "thoughts": thoughts, "cap": CAP}] if logged else []
    assert [{key: event[key] for key in ("section", "thoughts", "cap")} for event in over] == (
        expected
    )


def test_a_call_without_a_cap_logs_no_thinking_event(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    context = AgentContext(
        ws, job, "draft:3-1", Thinking(CAP * 10), "gemini-3.6-flash", "v1", synthetic=True
    )
    complete_json(context, Answer, "Draft", "text")
    assert not [event for event in _events(ws, job) if event["event"] == "ai_thinking_over_cap"]


def test_a_recording_keeps_thoughts_and_replays_them(tmp_path: Path) -> None:
    path = tmp_path / "recording.json"
    recording = RecordingProvider(Thinking(300), path)  # type: ignore[arg-type]
    live = recording.respond("gemini-3.6-flash", MESSAGES, (), synthetic=True)
    (row,) = json.loads(path.read_text(encoding="utf-8"))["responses"]
    assert row["usageMetadata"]["thoughtsTokenCount"] == 300
    assert row["usageMetadata"]["candidatesTokenCount"] == 20
    replayed = ReplayProvider(path).respond("gemini-3.6-flash", MESSAGES, ())
    assert live.output_tokens == replayed.output_tokens == 320
    assert replayed.thoughts_tokens == 300


def test_an_old_recording_without_thoughts_replays_as_zero(tmp_path: Path) -> None:
    path = tmp_path / "recording.json"
    RecordingProvider(Thinking(0), path).respond(  # type: ignore[arg-type]
        "gemini-3.6-flash", MESSAGES, (), synthetic=True
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["responses"][0]["usageMetadata"]["thoughtsTokenCount"]
    path.write_text(json.dumps(data), encoding="utf-8")
    replayed = ReplayProvider(path).respond("gemini-3.6-flash", MESSAGES, ())
    assert (replayed.output_tokens, replayed.thoughts_tokens) == (20, 0)
