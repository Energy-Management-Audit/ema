"""Official SDK adapters. Client construction is deliberately opt-in."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable, Mapping
from typing import Any, cast

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from openai import OpenAI
from openai.types.chat import ChatCompletion
from pydantic import SecretStr

from ema.core.errors import EmaError
from ema.core.llm.gemini_retry import call_with_retries, map_quota_or_credit_error
from ema.core.llm.models import selected_model
from ema.core.llm.types import Exchange, ToolCall, ToolSpec


def _live_key(key: SecretStr | None, llm_live: bool, environment: str) -> str:
    if not llm_live:
        raise EmaError("ai_offline", "AI aşteaptă activarea explicită.", "EMA_LLM_LIVE")
    if key is None or not key.get_secret_value():
        raise EmaError("ai_key_missing", "Cheia furnizorului AI lipseşte.", environment)
    return key.get_secret_value()


def _credit_error(exc: Exception, model: str) -> EmaError | None:
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", "")
    if (
        status == 402
        or code == 402
        or "monthly spending cap" in str(message).lower()
        or code
        in {
            "insufficient_quota",
            "billing_not_active",
            "credits_exhausted",
            "payment_required",
        }
    ):
        return EmaError("ai_credits", "Creditul furnizorului AI s-a epuizat.", model)
    return None


def _openai_messages(
    messages: list[dict[str, Any]], attachments: Mapping[str, bytes] | None = None
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        if message["role"] == "assistant" and message.get("tool_calls"):
            converted.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"]),
                            },
                        }
                        for call in message["tool_calls"]
                    ],
                }
            )
        elif message["role"] == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": message["tool_call_id"],
                    "content": json.dumps(message["content"], ensure_ascii=False),
                }
            )
        elif message.get("images"):
            images = message["images"]
            content: list[dict[str, Any]] = [{"type": "text", "text": str(message["content"])}]
            for image in images:
                sha = str(image["sha256"])
                media = str(image["media_type"])
                if attachments is None or sha not in attachments:
                    raise EmaError("image_missing", "Fotografia lipseşte.", sha)
                encoded = base64.b64encode(attachments[sha]).decode("ascii")
                content.append(
                    {"type": "image_url", "image_url": {"url": f"data:{media};base64,{encoded}"}}
                )
            converted.append({"role": message["role"], "content": content})
        else:
            converted.append({key: value for key, value in message.items() if key != "images"})
    return converted


class OpenAIProvider:
    name = "openai"

    _client_live = False

    def __init__(self, key: SecretStr | None, llm_live: bool, client_live: bool = False) -> None:
        self._client = OpenAI(api_key=_live_key(key, llm_live, "EMA_OPENAI_API_KEY"))
        self._client_live = client_live

    def respond(  # noqa: PLR0913
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: tuple[ToolSpec, ...],
        schema: dict[str, Any] | None = None,
        max_output_tokens: int = 4096,
        synthetic: bool = False,
        *,
        prompt_version: str = "",
        attachments: Mapping[str, bytes] | None = None,
        thinking_tokens: int | None = None,
    ) -> Exchange:
        del prompt_version, thinking_tokens
        if not synthetic and not self._client_live:
            raise EmaError(
                "ai_client_disabled", "Documentele clientului nu pot fi trimise la AI.", ""
            )
        request: dict[str, Any] = {
            "model": model,
            "messages": _openai_messages(messages, attachments),
            "max_completion_tokens": max_output_tokens,
        }
        request.update(selected_model("openai", model).request_options)
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
        if schema is not None:
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "ema_result", "schema": schema, "strict": True},
            }
        try:
            response = cast(ChatCompletion, self._client.chat.completions.create(**request))
        except Exception as exc:
            if credit_error := _credit_error(exc, model):
                raise credit_error from exc
            raise
        choice = response.choices[0].message
        calls = tuple(
            ToolCall(call.id, call.function.name, json.loads(call.function.arguments))
            for call in (choice.tool_calls or [])
            if call.type == "function"
        )
        usage = response.usage
        return Exchange(
            choice.content,
            calls,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
            cached_input_tokens=(usage.prompt_tokens_details.cached_tokens or 0)
            if usage and usage.prompt_tokens_details
            else 0,
        )


class GeminiProvider:
    name = "gemini"

    _client_live = False
    _sleep: Callable[[float], None] = staticmethod(time.sleep)

    def __init__(
        self,
        key: SecretStr | None,
        llm_live: bool,
        client_live: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        transport_retries: bool = True,
    ) -> None:
        self._client = genai.Client(api_key=_live_key(key, llm_live, "EMA_GEMINI_API_KEY"))
        self._client_live = client_live
        self._sleep = sleep
        self._transport_retries = transport_retries

    def respond(  # noqa: PLR0913, PLR0912, C901
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: tuple[ToolSpec, ...],
        schema: dict[str, Any] | None = None,
        max_output_tokens: int = 4096,
        synthetic: bool = False,
        *,
        prompt_version: str = "",
        attachments: Mapping[str, bytes] | None = None,
        thinking_tokens: int | None = None,
    ) -> Exchange:
        del prompt_version
        if not synthetic and not self._client_live:
            raise EmaError(
                "ai_client_disabled", "Documentele clientului nu pot fi trimise la AI.", ""
            )
        contents: list[types.Content] = []
        system: list[str] = []
        for message in messages:
            role = message["role"]
            if role == "system":
                system.append(str(message["content"]))
                continue
            if role == "tool":
                part = types.Part.from_function_response(
                    name=message["name"], response={"result": message["content"]}
                )
                if part.function_response is not None:
                    part.function_response.id = message["tool_call_id"]
                contents.append(types.Content(role="user", parts=[part]))
            elif role == "assistant" and message.get("tool_calls"):
                if content := message.get("provider_content"):
                    contents.append(types.Content.model_validate(content))
                else:
                    parts = [
                        types.Part.from_function_call(name=call["name"], args=call["arguments"])
                        for call in message["tool_calls"]
                    ]
                    contents.append(types.Content(role="model", parts=parts))
            else:
                parts = [types.Part.from_text(text=str(message["content"]))]
                for image in message.get("images", []):
                    sha = str(image["sha256"])
                    if attachments is None or sha not in attachments:
                        raise EmaError("image_missing", "Fotografia lipseşte.", sha)
                    parts.append(
                        types.Part.from_bytes(
                            data=attachments[sha], mime_type=str(image["media_type"])
                        )
                    )
                contents.append(
                    types.Content(
                        role="model" if role == "assistant" else "user",
                        parts=parts,
                    )
                )
        config: dict[str, Any] = {
            "system_instruction": "\n".join(system),
            "max_output_tokens": max_output_tokens,
        }
        if thinking_tokens is not None:
            # Gemini 3 ignores a token budget and thinks past it; it honours a level (#137).
            config["thinking_config"] = (
                types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
                if model.startswith("gemini-3")
                else types.ThinkingConfig(thinking_budget=thinking_tokens)
            )
        if tools:
            declarations = [
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters_json_schema=tool.parameters,
                )
                for tool in tools
            ]
            config["tools"] = [types.Tool(function_declarations=declarations)]
        if schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = schema

        def generate() -> Any:
            return self._client.models.generate_content(
                model=model,
                contents=cast(Any, contents),
                config=types.GenerateContentConfig(**config),
            )

        try:
            response = (
                call_with_retries(generate, model, self._sleep)
                if getattr(self, "_transport_retries", True)
                else generate()
            )
        except Exception as exc:
            if isinstance(exc, genai_errors.APIError) and (
                mapped := map_quota_or_credit_error(exc, model)
            ):
                raise mapped from exc
            if credit_error := _credit_error(exc, model):
                raise credit_error from exc
            raise
        calls = tuple(
            ToolCall(call.id or str(index), call.name or "", dict(call.args or {}))
            for index, call in enumerate(response.function_calls or [])
        )
        usage = response.usage_metadata
        candidate = response.candidates[0] if response.candidates else None
        return Exchange(
            response.text if not calls else None,
            calls,
            (usage.prompt_token_count or 0) if usage else 0,
            ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
            if usage
            else 0,
            candidate.content.model_dump(mode="json", exclude_none=True)
            if candidate and candidate.content
            else None,
            (usage.cached_content_token_count or 0) if usage else 0,
            candidate.finish_reason.name if candidate and candidate.finish_reason else None,
            (usage.thoughts_token_count or 0) if usage else 0,
        )
