"""Replay-only agent pass for unnumbered intake documents."""

from __future__ import annotations

from ema.audit.checklist import ChecklistItem
from ema.audit.dossier import dossier_documents
from ema.audit.intake_tools import IntakeDocument, IntakeTools
from ema.core.jobs import StageContext
from ema.core.llm import (
    AgentContext,
    Limits,
    ReplayProvider,
    agent_state,
    run_agent,
)


def classify_unplaced(
    ctx: StageContext,
    slots: dict[str, str],
    checklist: tuple[ChecklistItem, ...],
    replay: ReplayProvider,
    limits: Limits,
) -> tuple[IntakeTools, str]:
    documents = {
        name: IntakeDocument(name, document.text, page_images=document.page_images)
        for name, document in dossier_documents(ctx.ws, ctx.job, slots).items()
    }
    tools = IntakeTools(documents, {item.number: item.text for item in checklist})
    context = AgentContext(ctx.ws, ctx.job, "intake", replay, replay.model_id, "audit-intake-v1")
    previous = agent_state(ctx.ws, ctx.job, "intake")
    if previous is not None:
        tools.restore(previous.messages)
    state = run_agent(context, "Classify each file using verbatim evidence.", tools.tools(), limits)
    return tools, state.status
