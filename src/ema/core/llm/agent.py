"""Resumable, bounded tool-calling loop owned by Ema."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from ema.core.errors import EmaError
from ema.core.llm.models import Model, selected_model
from ema.core.llm.replay import ReplayProvider
from ema.core.llm.types import Exchange, Provider, ToolSpec
from ema.core.workspace import Workspace


@dataclass(frozen=True)
class Tool:
    spec: ToolSpec
    execute: Callable[[dict[str, Any]], object]


@dataclass(frozen=True)
class Limits:
    steps: int
    spend_cap_usd: float | None = None


@dataclass(frozen=True)
class AgentContext:
    ws: Workspace
    job: str
    section: str
    provider: Provider
    model_id: str
    prompt_version: str
    synthetic: bool = False
    client_live: bool = False


class AgentState(BaseModel):
    messages: list[dict[str, Any]]
    steps: int = 0
    cost_usd: float = 0
    status: str = "running"
    result: str | None = None
    step_limit: int = 0
    spend_cap_usd: float | None = None
    model_id: str = ""
    provider_name: str = ""
    prompt_version: str = ""


def _save(ws: Workspace, job: str, section: str, state: AgentState) -> None:
    with ws.connect() as db:
        db.execute(
            "INSERT INTO agent_sessions(job_id,section,state) VALUES(?,?,?) "
            "ON CONFLICT(job_id,section) DO UPDATE SET state=excluded.state",
            (job, section, state.model_dump_json()),
        )


def agent_state(ws: Workspace, job: str, section: str) -> AgentState | None:
    with ws.connect() as db:
        row = db.execute(
            "SELECT state FROM agent_sessions WHERE job_id=? AND section=?", (job, section)
        ).fetchone()
    return AgentState.model_validate_json(row[0]) if row else None


def record_call(
    context: AgentContext,
    exchange: Exchange,
    cost: float,
    duration_ms: int,
) -> None:
    with context.ws.connect() as db:
        db.execute(
            "INSERT INTO llm_calls(job_id,section,provider,model,prompt_version,"
            "input_tokens,output_tokens,estimated_cost_usd,duration_ms) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                context.job,
                context.section,
                context.provider.name,
                context.model_id,
                context.prompt_version,
                exchange.input_tokens,
                exchange.output_tokens,
                cost,
                duration_ms,
            ),
        )


def _reserve_cost(
    messages: list[dict[str, Any]],
    tools: Mapping[str, Tool],
    input_rate: float,
    output_rate: float,
) -> float:
    # Text-only intake: UTF-8 bytes conservatively bound tokenizer tokens, plus tool overhead.
    size = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
    size += len(json.dumps([tool.spec.parameters for tool in tools.values()]).encode("utf-8"))
    size += 4096
    return (size * input_rate + 4096 * output_rate) / 1_000_000


def _run_tools(state: AgentState, exchange: Exchange, tools: Mapping[str, Tool]) -> None:
    assistant: dict[str, Any] = {
        "role": "assistant",
        "tool_calls": [
            {"id": call.id, "name": call.name, "arguments": call.arguments}
            for call in exchange.calls
        ],
    }
    if exchange.provider_content is not None:
        assistant["provider_content"] = exchange.provider_content
    state.messages.append(assistant)
    for call in exchange.calls:
        tool = tools.get(call.name)
        if tool is None:
            result: object = {"error": "unknown_tool"}
        else:
            try:
                result = tool.execute(call.arguments)
            except (EmaError, ValidationError, ValueError, KeyError) as exc:
                result = {"error": exc.code if isinstance(exc, EmaError) else "invalid_arguments"}
        state.messages.append(
            {"role": "tool", "name": call.name, "tool_call_id": call.id, "content": result}
        )


def _cap_exceeded(
    state: AgentState,
    limits: Limits,
    tools: Mapping[str, Tool],
    model: Model,
) -> bool:
    return limits.spend_cap_usd is not None and (
        state.cost_usd + _reserve_cost(state.messages, tools, model.input_usd, model.output_usd)
        > limits.spend_cap_usd
    )


def _validate(context: AgentContext, limits: Limits) -> None:
    if context.provider.name != "replay" and not (context.synthetic or context.client_live):
        raise EmaError("ai_client_disabled", "Documentele clientului nu pot fi trimise la AI.", "")
    if limits.steps <= 0 or (limits.spend_cap_usd is not None and limits.spend_cap_usd <= 0):
        raise EmaError("ai_limits", "Limitele AI sunt invalide.", "")


def run_agent(  # noqa: C901
    context: AgentContext,
    instructions: str,
    tools: Mapping[str, Tool],
    limits: Limits,
    task: str | None = None,
) -> AgentState:
    _validate(context, limits)
    model = selected_model(
        context.provider.provider_name
        if isinstance(context.provider, ReplayProvider)
        else context.provider.name,
        context.model_id,
    )
    state = agent_state(context.ws, context.job, context.section) or AgentState(
        messages=[
            {"role": "system", "content": instructions},
            *([{"role": "user", "content": task}] if task is not None else []),
        ],
        model_id=context.model_id,
        provider_name=context.provider.name,
        prompt_version=context.prompt_version,
    )
    if (state.model_id, state.provider_name, state.prompt_version) != (
        context.model_id,
        context.provider.name,
        context.prompt_version,
    ):
        raise EmaError("ai_context_changed", "Configuraţia AI a etapei s-a schimbat.", "")
    state.step_limit, state.spend_cap_usd = limits.steps, limits.spend_cap_usd
    if state.status == "done":
        return state
    while True:
        if state.steps >= limits.steps:
            state.status = "step_limit"
            _save(context.ws, context.job, context.section, state)
            return state
        if _cap_exceeded(state, limits, tools, model):
            state.status = "spend_cap"
            _save(context.ws, context.job, context.section, state)
            return state
        started = time.monotonic()
        try:
            exchange = context.provider.respond(
                context.model_id,
                state.messages,
                tuple(tool.spec for tool in tools.values()),
                synthetic=context.synthetic,
                prompt_version=context.prompt_version,
            )
        except EmaError as exc:
            if exc.code == "replay_request_mismatch":
                raise
            state.status = "waiting_for_ai"
            _save(context.ws, context.job, context.section, state)
            raise EmaError(
                "ai_provider", "AI nu este disponibil; reluaţi etapa.", exc.code
            ) from exc
        except Exception as exc:
            state.status = "waiting_for_ai"
            _save(context.ws, context.job, context.section, state)
            raise EmaError(
                "ai_provider", "AI nu este disponibil; reluaţi etapa.", type(exc).__name__
            ) from exc
        duration_ms = int((time.monotonic() - started) * 1000)
        cost = model.cost(
            exchange.input_tokens, exchange.output_tokens, exchange.cached_input_tokens
        )
        record_call(context, exchange, cost, duration_ms)
        state.cost_usd += cost
        state.steps += 1
        if limits.spend_cap_usd is not None and state.cost_usd > limits.spend_cap_usd:
            state.status = "spend_cap"
            _save(context.ws, context.job, context.section, state)
            return state
        if exchange.calls:
            _run_tools(state, exchange, tools)
            _save(context.ws, context.job, context.section, state)
            continue
        state.result = exchange.text
        state.status = "done" if exchange.text is not None else "empty_response"
        _save(context.ws, context.job, context.section, state)
        return state
