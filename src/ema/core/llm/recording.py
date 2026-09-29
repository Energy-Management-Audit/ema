"""Capture provider exchanges in the replay file format."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ema.core.llm.replay import request_hashes
from ema.core.llm.types import Exchange, Provider, ToolSpec


class RecordingProvider:
    def __init__(self, inner: Provider, path: Path) -> None:
        self.inner = inner
        self.name = inner.name
        self.path = path
        self.format = (
            "gemini-generate-content" if inner.name == "gemini" else "openai-chat-completions"
        )

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
    ) -> Exchange:
        response = self.inner.respond(
            model,
            messages,
            tools,
            schema,
            max_output_tokens,
            synthetic,
            prompt_version=prompt_version,
            attachments=attachments,
        )
        row = self._row(response)
        row["model"] = model
        row["request_hashes"] = request_hashes(
            model, messages, tools, schema, max_output_tokens, prompt_version
        )
        data: dict[str, Any] = {"source": "recorded", "format": self.format, "responses": []}
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if loaded["source"] != "recorded" or loaded["format"] != self.format:
                raise ValueError("recording format differs from provider")
            data = loaded
        data["responses"].append(row)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)
        return response

    def _row(self, response: Exchange) -> dict[str, Any]:
        if self.format == "gemini-generate-content":
            parts = (
                response.provider_content.get("parts", [])
                if response.provider_content is not None
                else [{"text": response.text or ""}]
            )
            return {
                "candidates": [{"content": {"role": "model", "parts": parts}}],
                "usageMetadata": {
                    "promptTokenCount": response.input_tokens,
                    "candidatesTokenCount": response.output_tokens,
                    "cachedContentTokenCount": response.cached_input_tokens,
                },
            }
        return {
            "choices": [
                {
                    "message": {
                        "content": response.text,
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                                },
                            }
                            for call in response.calls
                        ],
                    }
                }
            ],
            "usage": {
                "prompt_tokens": response.input_tokens,
                "completion_tokens": response.output_tokens,
                "prompt_tokens_details": {"cached_tokens": response.cached_input_tokens},
            },
        }
