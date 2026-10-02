"""Live-AI switch, task turn, Gemini retries and the model list (no network)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors
from pydantic import BaseModel
from tests.workspace_jobs import create_job

from ema.api.error_status import STATUS
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.llm import AgentContext, Limits, complete_json, run_agent
from ema.core.llm.models import curated_models, selected_model
from ema.core.llm.providers import GeminiProvider, OpenAIProvider
from ema.core.llm.types import Exchange
from ema.core.workspace import Workspace

DISABLED = "Documentele clientului nu pot fi trimise la AI."


class Answer(BaseModel):
    item: int


class Live:
    name = "gemini"

    def __init__(self) -> None:
        self.seen: list[list[dict[str, Any]]] = []

    def respond(self, model: str, messages: list[dict[str, Any]], *args: object, **kw: object):
        self.seen.append([dict(message) for message in messages])
        return Exchange("done", (), 1, 1)


def _context(tmp_path: Path, provider: Live, **kwargs: bool) -> AgentContext:
    ws = Workspace(tmp_path / "workspace")
    job = create_job(ws, "audit", "synthetic", 2026)
    return AgentContext(ws, job, "s", provider, "gemini-3.8-flash", "v1", **kwargs)


@pytest.mark.parametrize(
    ("synthetic", "client_live", "allowed"),
    [(False, False, False), (True, False, True), (False, True, True), (True, True, True)],
)
def test_agent_and_structured_guard_matrix(
    tmp_path: Path, synthetic: bool, client_live: bool, allowed: bool
) -> None:
    context = _context(tmp_path, Live(), synthetic=synthetic, client_live=client_live)
    if allowed:
        run_agent(context, "Instructions", {}, Limits(2))
        return
    with pytest.raises(EmaError) as agent:
        run_agent(context, "Instructions", {}, Limits(2))
    assert (agent.value.code, agent.value.user_message_ro) == ("ai_client_disabled", DISABLED)
    with pytest.raises(EmaError) as structured:
        complete_json(context, Answer, "Classify", "text")
    assert structured.value.code == "ai_client_disabled"


@pytest.mark.parametrize("provider_type", [GeminiProvider, OpenAIProvider])
@pytest.mark.parametrize(
    ("synthetic", "client_live", "allowed"),
    [(False, False, False), (True, False, True), (False, True, True)],
)
def test_provider_guard_matrix(
    provider_type: Any, synthetic: bool, client_live: bool, allowed: bool
) -> None:
    provider = provider_type.__new__(provider_type)
    provider._client_live = client_live
    if provider_type is GeminiProvider:
        models = SimpleNamespace(
            generate_content=lambda **_: SimpleNamespace(
                function_calls=[], text="ok", usage_metadata=None, candidates=[]
            )
        )
        provider._client = SimpleNamespace(models=models)
        provider._sleep = lambda _: None
    else:
        choice = SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=[]))
        completions = SimpleNamespace(
            create=lambda **_: SimpleNamespace(choices=[choice], usage=None)
        )
        provider._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    model = next(m.id for m in curated_models() if m.provider == provider_type.name)
    messages = [{"role": "user", "content": "x"}]
    if allowed:
        assert provider.respond(model, messages, (), synthetic=synthetic).text == "ok"
        return
    with pytest.raises(EmaError) as error:
        provider.respond(model, messages, (), synthetic=synthetic)
    assert (error.value.code, error.value.user_message_ro) == ("ai_client_disabled", DISABLED)


def test_client_live_setting_is_environment_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EMA_AI_CLIENT_LIVE", raising=False)
    ws = Workspace(tmp_path)
    assert load_settings(ws).ai_client_live is False
    ws.settings_file().write_text("ai_client_live = true\n")
    assert load_settings(ws).ai_client_live is False
    monkeypatch.setenv("EMA_AI_CLIENT_LIVE", "true")
    assert load_settings(ws).ai_client_live is True


def test_task_opens_with_a_user_turn_and_default_keeps_the_old_state(tmp_path: Path) -> None:
    with_task, without = Live(), Live()
    run_agent(
        _context(tmp_path / "a", with_task, synthetic=True), "Sys", {}, Limits(2), task="Do s"
    )
    run_agent(_context(tmp_path / "b", without, synthetic=True), "Sys", {}, Limits(2))
    assert with_task.seen[0] == [
        {"role": "system", "content": "Sys"},
        {"role": "user", "content": "Do s"},
    ]
    assert without.seen[0] == [{"role": "system", "content": "Sys"}]


def _api_error(code: int, *details: dict[str, Any]) -> errors.APIError:
    return errors.APIError(code, {"error": {"code": code, "details": list(details)}})


def _delay(value: str) -> dict[str, Any]:
    return {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": value}


def _quota(quota_id: str) -> dict[str, Any]:
    return {
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [{"quotaId": quota_id}],
    }


def _gemini(outcomes: list[object]) -> tuple[GeminiProvider, list[float], list[None]]:
    sleeps: list[float] = []
    calls: list[None] = []

    def generate(**_: object) -> object:
        calls.append(None)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    provider = GeminiProvider.__new__(GeminiProvider)
    provider._client = SimpleNamespace(models=SimpleNamespace(generate_content=generate))
    provider._client_live = True
    provider._sleep = sleeps.append
    return provider, sleeps, calls


OK = SimpleNamespace(function_calls=[], text="ok", usage_metadata=None, candidates=[])
MESSAGES = [{"role": "user", "content": "x"}]


def test_429_waits_the_retry_delay_then_succeeds() -> None:
    provider, sleeps, _ = _gemini(
        [_api_error(429, _delay("12s")), _api_error(429, _delay("0.5s")), OK]
    )
    assert provider.respond("gemini-3.8-flash", MESSAGES, ()).text == "ok"
    assert sleeps == [12.0, 0.5]


def test_429_delay_is_capped_and_attempts_are_four() -> None:
    failure = [_api_error(429, _delay("300s")) for _ in range(4)]
    provider, sleeps, calls = _gemini(failure)
    with pytest.raises(errors.APIError):
        provider.respond("gemini-3.8-flash", MESSAGES, ())
    assert sleeps == [60.0, 60.0, 60.0]
    assert len(calls) == 4


def test_per_day_quota_fails_at_once() -> None:
    provider, sleeps, calls = _gemini(
        [_api_error(429, _quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier"), _delay("5s"))]
    )
    with pytest.raises(EmaError) as error:
        provider.respond("gemini-3.8-flash", MESSAGES, ())
    assert error.value.code == "ai_quota_day"
    assert error.value.user_message_ro == "Cota zilnică a furnizorului AI s-a epuizat."
    assert error.value.detail == "gemini-3.8-flash"
    assert sleeps == [] and len(calls) == 1


def test_per_minute_quota_is_retried() -> None:
    provider, sleeps, _ = _gemini(
        [_api_error(429, _quota("GenerateRequestsPerMinutePerProjectPerModel"), _delay("3s")), OK]
    )
    assert provider.respond("gemini-3.8-flash", MESSAGES, ()).text == "ok"
    assert sleeps == [3.0]


def test_5xx_backs_off_then_raises_unavailable() -> None:
    provider, sleeps, calls = _gemini(
        [_api_error(503), _api_error(500), _api_error(503), _api_error(503)]
    )
    with pytest.raises(EmaError) as error:
        provider.respond("gemini-3.8-flash", MESSAGES, ())
    assert error.value.code == "ai_unavailable"
    assert error.value.user_message_ro == "Furnizorul AI nu răspunde acum."
    assert error.value.detail == "gemini-3.8-flash"
    assert sleeps == [10.0, 20.0, 40.0]
    assert len(calls) == 4


def test_5xx_recovers() -> None:
    provider, sleeps, _ = _gemini([_api_error(503), OK])
    assert provider.respond("gemini-3.8-flash", MESSAGES, ()).text == "ok"
    assert sleeps == [10.0]


def test_other_errors_pass_through() -> None:
    provider, sleeps, _ = _gemini([_api_error(400)])
    with pytest.raises(errors.APIError):
        provider.respond("gemini-3.8-flash", MESSAGES, ())
    assert sleeps == []


def test_error_codes_have_their_status() -> None:
    assert (STATUS["ai_quota_day"], STATUS["ai_unavailable"]) == (429, 503)


def test_new_gemini_model_is_the_standard_default_and_old_one_stays() -> None:
    model = selected_model("gemini", "gemini-3.8-flash")
    assert (model.tier, model.vision) == ("standard", True)
    assert (model.input_usd, model.cached_input_usd, model.output_usd) == (0.75, 0.075, 3.75)
    standard = [m.id for m in curated_models() if m.provider == "gemini" and m.tier == "standard"]
    assert standard[0] == "gemini-3.8-flash"
    assert selected_model("gemini", "gemini-3.6-flash").id == "gemini-3.6-flash"
