"""Synthetic-only audit Draft agent with fact, style and write tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ema.audit.catalogue import CATALOGUE
from ema.audit.draft_checks import DraftCheck, DraftReview, check_draft, support_pass
from ema.audit.draft_schema import SECTION_FACTS, SectionDraft
from ema.core.errors import EmaError
from ema.core.llm import AgentContext, Limits, ReplayProvider, run_agent
from ema.core.llm.agent import AgentState, Tool
from ema.core.llm.types import Provider, ToolSpec
from ema.core.resources import resource_path
from ema.core.review.models import Field
from ema.core.workspace import Workspace

PROMPT_VERSION = "audit-draft-v1"
INSTRUCTIONS = (
    "Draft only the requested section from recorded facts. Read facts and the style guide first. "
    "Use {{f:fact_id}} for every number and client-specific name; list supporting fact ids on "
    "every paragraph, table cell and caption. Never use web tools or invent missing facts. "
    "Write a structured section draft with status missing when a needed fact is absent."
)


def recorded_facts(ws: Workspace, job: str, section: str) -> dict[str, Field]:
    allowed = SECTION_FACTS[section]
    with ws.connect() as db:
        rows = db.execute("SELECT key,data FROM fields WHERE job_id=?", (job,))
        return {
            str(row["key"]): Field.model_validate_json(row["data"])
            for row in rows
            if str(row["key"]) in allowed
        }


class DraftTools:
    def __init__(
        self, ws: Workspace, job: str, section: str, facts: dict[str, Field] | None = None
    ) -> None:
        if section not in SECTION_FACTS:
            raise EmaError("section_missing", "Secţiunea de redactare lipseşte.", section)
        self.ws, self.job, self.section = ws, job, section
        self.facts = recorded_facts(ws, job, section) if facts is None else facts
        self.draft: SectionDraft | None = None
        self.check: DraftCheck | None = None

    def read_facts(self, _args: dict[str, Any]) -> object:
        return [
            {
                "id": key,
                "value": str(field.value) if field.presence == "found" else None,
                "unit": field.unit,
                "presence": field.presence,
                "evidence_ids": field.evidence,
            }
            for key, field in self.facts.items()
        ]

    def read_style_guide(self, _args: dict[str, Any]) -> object:
        return json.loads(
            resource_path("audit", "prompts", "style_guide_v1.json").read_text(encoding="utf-8")
        )

    def write_section_draft(self, args: dict[str, Any]) -> object:
        draft = SectionDraft.model_validate(args)
        if draft.section != self.section:
            raise EmaError("draft_section", "Secţiunea redactată nu corespunde.", self.section)
        check = check_draft(draft, self.facts, self.job)
        if check.fatal:
            return {"accepted": False, "errors": [issue.code for issue in check.fatal]}
        self.draft, self.check = draft, check
        return {"accepted": True, "coverage": check.coverage}

    def tools(self) -> dict[str, Tool]:
        obj: dict[str, Any] = {"type": "object", "properties": {}}
        return {
            "read_facts": Tool(
                ToolSpec("read_facts", "Read recorded section facts", obj), self.read_facts
            ),
            "read_style_guide": Tool(
                ToolSpec("read_style_guide", "Read versioned writing patterns", obj),
                self.read_style_guide,
            ),
            "write_section_draft": Tool(
                ToolSpec(
                    "write_section_draft",
                    "Validate and record a structured section draft",
                    SectionDraft.model_json_schema(),
                ),
                self.write_section_draft,
            ),
        }


def draft_task(section: str) -> str:
    """The turn that opens a live draft pass; without it the model has to guess the section id."""
    title = next(item.title for item in CATALOGUE if item.id == section)
    return (
        f"Redactează secţiunea {section} „{title}”. "
        f"Câmpul section din write_section_draft este exact „{section}”."
    )


def draft_section_run(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    section: str,
    draft_provider: Provider,
    support_provider: Provider,
    limits: Limits,
    *,
    model_id: str,
    support_model_id: str | None = None,
    facts: dict[str, Field] | None = None,
    synthetic: bool = False,
    client_live: bool = False,
    task: str | None = None,
) -> tuple[AgentState, SectionDraft, DraftCheck, tuple[DraftReview, ...]]:
    """Run the Draft pass and the support pass against the given providers."""
    tools = DraftTools(ws, job, section, facts)
    context = AgentContext(
        ws,
        job,
        f"draft:{section}",
        draft_provider,
        model_id,
        PROMPT_VERSION,
        synthetic=synthetic,
        client_live=client_live,
    )
    state = run_agent(context, INSTRUCTIONS, tools.tools(), limits, task=task)
    if state.status == "done" and tools.draft is None:
        accepted = {
            message["tool_call_id"]
            for message in state.messages
            if message["role"] == "tool"
            and message["name"] == "write_section_draft"
            and message["content"].get("accepted") is True
        }
        for message in state.messages:
            if message["role"] != "assistant":
                continue
            for call in message.get("tool_calls", []):
                if call["id"] in accepted and call["name"] == "write_section_draft":
                    tools.write_section_draft(call["arguments"])
    if state.status != "done" or tools.draft is None or tools.check is None:
        raise EmaError("draft_incomplete", "Redactarea secţiunii nu s-a încheiat.", section)
    support_context = AgentContext(
        ws,
        job,
        f"support:{section}",
        support_provider,
        support_model_id or model_id,
        PROMPT_VERSION + "-support",
        synthetic=synthetic,
        client_live=client_live,
    )
    flags = support_pass(support_context, tools.draft, tools.facts)
    return state, tools.draft, tools.check, flags


def draft_section_replay(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    section: str,
    draft_recording: Path,
    support_recording: Path,
    limits: Limits,
    *,
    model_id: str | None = None,
    facts: dict[str, Field] | None = None,
) -> tuple[AgentState, SectionDraft, DraftCheck, tuple[DraftReview, ...]]:
    """Run request-bound Draft and support replay; replay recordings never reach a provider."""
    draft_provider, support_provider = (
        ReplayProvider(draft_recording),
        ReplayProvider(support_recording),
    )
    return draft_section_run(
        ws,
        job,
        section,
        draft_provider,
        support_provider,
        limits,
        model_id=model_id or draft_provider.model_id,
        support_model_id=model_id or support_provider.model_id,
        facts=facts,
        synthetic=True,
    )
