"""Recorded structured-output validation and privacy gate."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import BaseModel
from tests.workspace_jobs import create_job

from ema.core.errors import EmaError
from ema.core.llm import AgentContext, ReplayProvider, complete_json
from ema.core.llm.agent import call_with_budget
from ema.core.llm.models import selected_model
from ema.core.llm.replay import request_hashes
from ema.core.llm.types import Exchange
from ema.core.workspace import Workspace


class Classification(BaseModel):
    item: int


def _replay(path: Path, texts: list[str]) -> ReplayProvider:
    messages = [
        {"role": "system", "content": "Classify"},
        {"role": "user", "content": "Synthetic permit"},
    ]
    responses = [
        {
            "request_hashes": request_hashes(
                "gemini-3.6-flash",
                messages
                + (
                    [
                        {"role": "assistant", "content": texts[0]},
                        {"role": "user", "content": "Return valid JSON for the schema."},
                    ]
                    if index
                    else []
                ),
                (),
                Classification.model_json_schema(),
                4096,
                "v1",
            ),
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 5},
        }
        for index, text in enumerate(texts)
    ]
    path.write_text(
        json.dumps(
            {"source": "hand-authored", "format": "openai-chat-completions", "responses": responses}
        ),
        encoding="utf-8",
    )
    return ReplayProvider(path)


def test_complete_json_retries_once_and_logs_both_calls(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    provider = _replay(tmp_path / "responses.json", ['{"item": "wrong"}', '{"item": 2}'])
    context = AgentContext(ws, job, "classification", provider, "gemini-3.6-flash", "v1")
    assert complete_json(context, Classification, "Classify", "Synthetic permit").item == 2
    assert provider.calls == 2
    with ws.connect() as db:
        count = db.execute("SELECT count(*) FROM llm_calls WHERE job_id=?", (job,)).fetchone()[0]
    assert count == 2


def test_complete_json_surfaces_second_schema_error(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    provider = _replay(tmp_path / "responses.json", ['{"item": "wrong"}'] * 2)
    context = AgentContext(ws, job, "classification", provider, "gemini-3.6-flash", "v1")
    with pytest.raises(EmaError) as error:
        complete_json(context, Classification, "Classify", "Synthetic permit")
    assert error.value.code == "ai_schema"


def test_complete_json_checks_budget_before_initial_call_and_schema_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    provider = _replay(tmp_path / "responses.json", ['{"item": "wrong"}', '{"item": 2}'])
    context = AgentContext(ws, job, "classification", provider, "gemini-3.6-flash", "v1")
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", "0")
    with pytest.raises(EmaError) as initial:
        complete_json(context, Classification, "Classify", "Synthetic permit")
    assert initial.value.code == "ai_budget"
    assert provider.calls == 0

    first_cost = selected_model("gemini", "gemini-3.6-flash").cost(5, 5)
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", str(first_cost))
    with pytest.raises(EmaError) as retry:
        complete_json(context, Classification, "Classify", "Synthetic permit")
    assert (retry.value.code, retry.value.user_message_ro) == (
        "ai_budget",
        "Bugetul AI al lucrării s-a epuizat.",
    )
    assert provider.calls == 1


def test_live_provider_cannot_receive_client_content(tmp_path: Path) -> None:
    class FakeLive:
        name = "gemini"

        def respond(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("must not be called")

    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    context = AgentContext(ws, job, "classification", FakeLive(), "gemini-3.6-flash", "v1")
    with pytest.raises(EmaError) as error:
        complete_json(context, Classification, "Classify", "Confidential text")
    assert error.value.code == "ai_client_disabled"


def test_concurrent_estimates_share_the_locked_spend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    provider = _replay(tmp_path / "responses.json", ['{"item": 1}'])
    context = AgentContext(ws, job, "classification", provider, "gemini-3.6-flash", "v1")
    model = selected_model("gemini", "gemini-3.6-flash")
    cost = model.cost(4_000, 4_000)
    monkeypatch.setenv("EMA_AI_JOB_BUDGET_USD", str(cost * 1.5))
    calls: list[int] = []

    def one() -> str:
        try:
            call_with_budget(
                context,
                model,
                lambda: (calls.append(1), Exchange("ok", (), 4_000, 4_000))[1],
                estimate=lambda: (4_000, cost),
            )
        except EmaError as error:
            return error.code
        return "ok"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: one(), range(2)))
    assert sorted(outcomes) == ["ai_budget", "ok"]
    assert len(calls) == 1
