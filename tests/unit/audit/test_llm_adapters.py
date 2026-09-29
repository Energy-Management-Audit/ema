"""SDK request construction without network access."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from google.genai import types

from ema.core.errors import EmaError
from ema.core.llm.models import curated_models
from ema.core.llm.providers import GeminiProvider, OpenAIProvider
from ema.core.llm.types import ToolSpec


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


@pytest.mark.parametrize("provider_type", [GeminiProvider, OpenAIProvider])
def test_live_adapters_refuse_unmarked_content(provider_type: type[object]) -> None:
    provider = provider_type.__new__(provider_type)
    with pytest.raises(EmaError) as error:
        provider.respond("unused", [{"role": "user", "content": "client text"}], ())
    assert error.value.code == "ai_client_disabled"
