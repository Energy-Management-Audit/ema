"""Validated JSON responses with one schema retry."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from ema.core.errors import EmaError
from ema.core.llm.agent import AgentContext, call_with_budget
from ema.core.llm.models import selected_model
from ema.core.llm.replay import ReplayProvider
from ema.core.llm.types import ImageInput


def complete_json[T: BaseModel](  # noqa: PLR0913
    context: AgentContext,
    schema: type[T],
    prompt: str,
    content: str,
    *,
    images: tuple[ImageInput, ...] = (),
    max_output_tokens: int | None = None,
    estimate_tokens: Callable[[list[dict[str, Any]]], int] | None = None,
    on_estimate: Callable[[int, float, float], None] | None = None,
    schema_retries: int = 1,
    thinking_tokens: int | None = None,
) -> T:
    if context.provider.name != "replay" and not (context.synthetic or context.client_live):
        raise EmaError("ai_client_disabled", "Documentele clientului nu pot fi trimise la AI.", "")
    model = selected_model(
        context.provider.provider_name
        if isinstance(context.provider, ReplayProvider)
        else context.provider.name,
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
    draft_call = context.section.startswith(("draft:", "support:"))
    # A draft or support call is sized by its caller (D2); 8,000 is only its default.
    default_limit = 8000 if draft_call and context.provider.name != "replay" else 4096
    output_limit = default_limit if max_output_tokens is None else max_output_tokens
    budget_estimate_tokens = estimate_tokens
    if draft_call and estimate_tokens is None:
        schema_size = len(json.dumps(schema.model_json_schema()).encode("utf-8"))

        def draft_estimate_tokens(messages: list[dict[str, Any]]) -> int:
            size = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
            return (size + schema_size + 3) // 4

        budget_estimate_tokens = draft_estimate_tokens
    budget_on_estimate = on_estimate
    if draft_call and on_estimate is None:

        def log_draft_estimate(_tokens: int, projected: float, spent: float) -> None:
            logging.getLogger(__name__).info(
                "draft preflight estimated_cost_usd=%.6f spent_usd=%.6f", projected, spent
            )

        budget_on_estimate = log_draft_estimate
    for attempt in range(schema_retries + 1):
        kwargs: dict[str, Any] = ({"attachments": attachments} if images else {}) | (
            {"thinking_tokens": thinking_tokens} if thinking_tokens is not None else {}
        )
        response = call_with_budget(
            context,
            model,
            lambda kwargs=kwargs: context.provider.respond(
                context.model_id,
                messages,
                (),
                schema.model_json_schema(),
                output_limit,
                synthetic=context.synthetic,
                prompt_version=context.prompt_version,
                **kwargs,
            ),
            estimate=(
                (
                    lambda: (
                        (tokens := budget_estimate_tokens(messages)),
                        model.cost(tokens, output_limit),
                    )
                )
                if budget_estimate_tokens is not None
                else None
            ),
            on_estimate=budget_on_estimate,
        )
        if response.finish_reason == "MAX_TOKENS":
            logging.getLogger(__name__).warning("ai_truncated section=%s", context.section)
            raise EmaError("ai_truncated", "Răspunsul AI a fost întrerupt.", context.section)
        try:
            return schema.model_validate(json.loads(response.text or ""))
        except (ValidationError, ValueError) as exc:
            if attempt == schema_retries:
                raise EmaError(
                    "ai_schema", "Răspunsul AI nu respectă formatul cerut.", type(exc).__name__
                ) from exc
            messages.append({"role": "assistant", "content": response.text or ""})
            messages.append({"role": "user", "content": "Return valid JSON for the schema."})
    raise AssertionError("unreachable")
