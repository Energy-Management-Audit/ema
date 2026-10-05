"""SDK request construction without network access."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import types

from ema.audit.draft_plan import THINKING_TOKENS
from ema.core.errors import EmaError
from ema.core.llm.models import curated_models
from ema.core.llm.providers import GeminiProvider, OpenAIProvider
from ema.core.llm.types import Exchange, ToolSpec


def test_gemini_keeps_signed_function_history_and_call_id() -> None:
    signed = types.Part.from_function_call(name="read_file", args={"name": "synthetic.txt"})
    signed.thought_signature = b"signature"
    content = types.Content(role="model", parts=[signed])
    captured = {}

    class Models:
        def generate_content(self, **kwargs: object) -> object:
            captured.update(kwargs)
            return SimpleNamespace(
                function_calls=[], text="done", usage_metadata=None, candidates=[]
            )

    provider = GeminiProvider.__new__(GeminiProvider)
    provider._client = SimpleNamespace(models=Models())
    result = provider.respond(
        next(model.id for model in curated_models() if model.provider == "openai"),
        [
            {"role": "system", "content": "Read files"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "f1", "name": "read_file", "arguments": {"name": "synthetic.txt"}}
                ],
                "provider_content": content.model_dump(mode="json", exclude_none=True),
            },
            {
                "role": "tool",
                "name": "read_file",
                "tool_call_id": "f1",
                "content": {"text": "synthetic"},
            },
        ],
        (ToolSpec("read_file", "Read", {"type": "object", "properties": {}}),),
        synthetic=True,
    )
    contents = captured["contents"]
    assert contents[0].parts[0].thought_signature == b"signature"
    assert contents[1].parts[0].function_response.id == "f1"
    assert result.text == "done"


def _gemini_configs(model: str) -> tuple[list[types.GenerateContentConfig], list[Exchange]]:
    configs: list[types.GenerateContentConfig] = []

    class Models:
        def generate_content(self, **kwargs: object) -> object:
            configs.append(kwargs["config"])  # type: ignore[arg-type]
            return SimpleNamespace(
                function_calls=[],
                text='{"item": 1}',
                usage_metadata=SimpleNamespace(
                    prompt_token_count=10,
                    candidates_token_count=20,
                    thoughts_token_count=300,
                    cached_content_token_count=None,
                ),
                candidates=[
                    SimpleNamespace(content=None, finish_reason=types.FinishReason.MAX_TOKENS)
                ],
            )

    provider = GeminiProvider.__new__(GeminiProvider)
    provider._client = SimpleNamespace(models=Models())
    results = [
        provider.respond(
            model,
            [{"role": "user", "content": "synthetic draft"}],
            (),
            synthetic=True,
            thinking_tokens=thinking,
        )
        for thinking in (THINKING_TOKENS, None)
    ]
    return configs, results


def test_gemini_3_thinks_at_a_low_level_and_reports_its_thoughts() -> None:
    configs, results = _gemini_configs("gemini-3.8-flash")
    assert configs[0].thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert configs[0].thinking_config.thinking_budget is None
    assert configs[1].thinking_config is None
    assert [result.finish_reason for result in results] == ["MAX_TOKENS", "MAX_TOKENS"]
    # Thoughts are billed as output and reported apart.
    assert (results[0].output_tokens, results[0].thoughts_tokens) == (320, 300)


def test_older_gemini_keeps_the_thinking_budget() -> None:
    configs, _ = _gemini_configs("gemini-2.5-flash")
    assert configs[0].thinking_config.thinking_budget == THINKING_TOKENS
    assert configs[0].thinking_config.thinking_level is None
    assert configs[1].thinking_config is None


def test_openai_rebuilds_function_messages_for_sdk() -> None:
    captured = {}

    class Completions:
        def create(self, **kwargs: object) -> object:
            captured.update(kwargs)
            choice = SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]))
            return SimpleNamespace(choices=[choice], usage=None)

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    provider.respond(
        next(model.id for model in curated_models() if model.provider == "openai"),
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "f1", "name": "read_file", "arguments": {"name": "synthetic.txt"}}
                ],
            },
            {
                "role": "tool",
                "name": "read_file",
                "tool_call_id": "f1",
                "content": {"text": "synthetic"},
            },
        ],
        (),
        synthetic=True,
    )
    messages = captured["messages"]
    assert messages[0]["tool_calls"][0]["function"]["arguments"] == '{"name": "synthetic.txt"}'
    assert messages[1]["content"] == '{"text": "synthetic"}'


def test_openai_maps_provider_402_without_exposing_response_body() -> None:
    class Completions:
        def create(self, **kwargs: object) -> object:
            raise type(
                "ProviderError",
                (Exception,),
                {"status_code": 402, "code": "insufficient_quota", "body": "private body"},
            )("payment required")

    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    with pytest.raises(EmaError) as error:
        provider.respond(
            next(model.id for model in curated_models() if model.provider == "openai"),
            [{"role": "user", "content": "synthetic"}],
            (),
            synthetic=True,
        )
    assert error.value.code == "ai_credits"
    assert error.value.user_message_ro == "Creditul furnizorului AI s-a epuizat."
    assert error.value.detail == next(
        model.id for model in curated_models() if model.provider == "openai"
    )
    assert error.value.__cause__.code == "insufficient_quota"


@pytest.mark.parametrize("provider_type", [GeminiProvider, OpenAIProvider])
def test_live_adapters_refuse_unmarked_content(provider_type: type[object]) -> None:
    provider = provider_type.__new__(provider_type)
    with pytest.raises(EmaError) as error:
        provider.respond("unused", [{"role": "user", "content": "client text"}], ())
    assert error.value.code == "ai_client_disabled"
