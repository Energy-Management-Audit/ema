"""Small provider boundary shared by live and replay calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Exchange:
    text: str | None
    calls: tuple[ToolCall, ...]
    input_tokens: int
    output_tokens: int
    provider_content: dict[str, Any] | None = None
    cached_input_tokens: int = 0


class Provider(Protocol):
    name: str

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
    ) -> Exchange: ...
