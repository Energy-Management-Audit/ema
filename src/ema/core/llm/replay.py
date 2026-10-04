"""Offline recorded exchanges; no network or SDK construction."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from ema.core.errors import EmaError
from ema.core.llm.models import curated_models
from ema.core.llm.types import Exchange, ToolCall, ToolSpec


def request_hashes(
    model: str,
    messages: list[dict[str, Any]],
    tools: tuple[ToolSpec, ...],
    schema: dict[str, Any] | None,
    max_output_tokens: int,
    prompt_version: str,
) -> dict[str, str]:
    parts: dict[str, object] = {
        "model": model,
        "prompt_version": prompt_version,
        "messages": messages,
        "tools": [vars(tool) for tool in tools],
        "schema": schema,
        "max_output_tokens": max_output_tokens,
    }
    return {
        name: hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        for name, value in parts.items()
    }


class ReplayProvider:
    name = "replay"

    def __init__(self, recording: Path) -> None:
        loaded: object = json.loads(recording.read_text(encoding="utf-8"))
        data = cast(dict[str, Any], loaded) if isinstance(loaded, dict) else {}
        if not isinstance(data.get("responses"), list):
            raise EmaError("replay_invalid", "Înregistrarea AI este invalidă.", "shape")
        if data.get("source") not in {"recorded", "hand-authored"}:
            raise EmaError("replay_invalid", "Înregistrarea AI este invalidă.", "source")
        if data.get("format") not in {"openai-chat-completions", "gemini-generate-content"}:
            raise EmaError("replay_invalid", "Formatul înregistrării AI este invalid.", "")
        self._responses: list[dict[str, Any]] = data["responses"]
        self._format: str = data["format"]
        self.source: str = data["source"]
        self._model_id: str | None = data.get("model")
        self.calls = 0

    @property
    def model_id(self) -> str:
        if self._model_id:
            return self._model_id
        ids = {row["model"] for row in self._responses if isinstance(row.get("model"), str)}
        if len(ids) == 1:
            return str(ids.pop())
        hashes = {row.get("request_hashes", {}).get("model") for row in self._responses}
        matches = [
            model.id
            for model in curated_models()
            if hashlib.sha256(json.dumps(model.id).encode()).hexdigest() in hashes
        ]
        if len(matches) == 1:
            return matches[0]
        raise EmaError("replay_invalid", "Modelul înregistrării lipseşte.", "model")

    @property
    def provider_name(self) -> str:
        for model in curated_models():
            if model.id == self.model_id:
                return model.provider
        raise EmaError("model_unknown", "Modelul ales nu este disponibil.", self.model_id)

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
        del synthetic, attachments, thinking_tokens
        if self.calls >= len(self._responses):
            raise EmaError("replay_exhausted", "Răspunsurile AI înregistrate s-au terminat.", "")
        row = self._responses[self.calls]
        actual = request_hashes(model, messages, tools, schema, max_output_tokens, prompt_version)
        expected = row.get("request_hashes", {})
        for part, digest in actual.items():
            if expected.get(part) != digest:
                raise EmaError(
                    "replay_request_mismatch",
                    "Cererea AI nu corespunde înregistrării.",
                    f"request {part}",
                )
        self.calls += 1
        if self._format == "gemini-generate-content":
            content = row["candidates"][0]["content"]
            parts = content["parts"]
            usage = row["usageMetadata"]
            return Exchange(
                "".join(part["text"] for part in parts if "text" in part) or None,
                tuple(
                    ToolCall(
                        str(part["functionCall"].get("id", index)),
                        part["functionCall"]["name"],
                        part["functionCall"].get("args", {}),
                    )
                    for index, part in enumerate(parts)
                    if "functionCall" in part
                ),
                int(usage["promptTokenCount"]),
                int(usage.get("candidatesTokenCount", 0)) + int(usage.get("thoughtsTokenCount", 0)),
                content,
                int(usage.get("cachedContentTokenCount", 0)),
                row["candidates"][0].get("finishReason"),
            )
        message = row["choices"][0]["message"]
        usage = row["usage"]
        return Exchange(
            message.get("content"),
            tuple(
                ToolCall(
                    call["id"], call["function"]["name"], json.loads(call["function"]["arguments"])
                )
                for call in message.get("tool_calls", [])
            ),
            int(usage["prompt_tokens"]),
            int(usage["completion_tokens"]),
            cached_input_tokens=int(usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)),
            finish_reason=row["choices"][0].get("finish_reason"),
        )
