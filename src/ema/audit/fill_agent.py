"""Replay-only entry point for a synthetic dossier's per-section Fill stage."""

from __future__ import annotations

from ema.audit.fill_tools import FillDocument, FillTools
from ema.audit.sections import record_applicability
from ema.core.llm import AgentContext, Limits, ReplayProvider, run_agent
from ema.core.llm.agent import AgentState
from ema.core.workspace import Workspace

PROMPT_VERSION = "audit-fill-v1"
INSTRUCTIONS = (
    "Read the dossier and dataset for this section. Record facts only with verbatim "
    "source quotes or an exact dataset field. Mark missing facts, defer unavailable "
    "material, and propose n/a only when the catalogue trigger is absent. "
    "Never infer a number that is not in a source."
)


def fill_section_replay(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    section: str,
    documents: dict[str, FillDocument],
    replay: ReplayProvider,
    limits: Limits,
    *,
    model_id: str = "gemini-3.6-flash",
) -> tuple[AgentState, FillTools]:
    """Run only on a synthetic dossier; S11 persists the resumable transcript."""
    record_applicability(ws, job, section)
    tools = FillTools(ws, job, section, documents)
    context = AgentContext(ws, job, section, replay, model_id, PROMPT_VERSION, synthetic=True)
    return run_agent(context, INSTRUCTIONS, tools.tools(), limits), tools
