"""Validated JSON responses with one schema retry."""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from ema.core.errors import EmaError
from ema.core.llm.agent import AgentContext, record_call
from ema.core.llm.models import selected_model
from ema.core.llm.types import ImageInput


def complete_json[T: BaseModel](
    context: AgentContext,
    schema: type[T],
    prompt: str,
    content: str,
    *,
    images: tuple[ImageInput, ...] = (),
) -> T:
    if context.provider.name != "replay" and not (context.synthetic or context.client_live):
        raise EmaError("ai_client_disabled", "Documentele clientului nu pot fi trimise la AI.", "")
    model = selected_model(
        context.provider.name if context.provider.name != "replay" else "gemini",
        context.model_id,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": content,
            **(
                {
                    "images": [
                        {"sha256": image.sha256, "media_type": image.media_type} for image in images
                    ]
                }
                if images
                else {}
            ),
        },
    ]
    attachments = {image.sha256: image.data for image in images}
    for attempt in range(2):
        started = time.monotonic()
        kwargs: dict[str, Any] = {"attachments": attachments} if images else {}
        response = context.provider.respond(
            context.model_id,
            messages,
            (),
            schema.model_json_schema(),
            synthetic=context.synthetic,
            prompt_version=context.prompt_version,
            **kwargs,
        )
        record_call(
            context,
            response,
            model.cost(response.input_tokens, response.output_tokens, response.cached_input_tokens),
            int((time.monotonic() - started) * 1000),
        )
        try:
            return schema.model_validate(json.loads(response.text or ""))
        except (ValidationError, ValueError) as exc:
            if attempt:
                raise EmaError(
                    "ai_schema", "Răspunsul AI nu respectă formatul cerut.", type(exc).__name__
                ) from exc
            messages.append({"role": "assistant", "content": response.text or ""})
            messages.append({"role": "user", "content": "Return valid JSON for the schema."})
    raise AssertionError("unreachable")
