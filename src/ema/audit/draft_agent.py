"""Structured audit Draft call and the separate support check."""

from __future__ import annotations

import json
from pathlib import Path

from ema.audit.catalogue import CATALOGUE
from ema.audit.catalogue_types import fact_key
from ema.audit.draft_checks import DraftCheck, DraftReview, check_draft, support_pass
from ema.audit.draft_schema import SECTION_FACTS, SectionDraft
from ema.audit.draft_style import configured_style_example
from ema.core.errors import EmaError
from ema.core.llm import AgentContext, ReplayProvider, complete_json
from ema.core.llm.agent import AgentState
from ema.core.llm.types import Provider
from ema.core.resources import resource_path
from ema.core.review.models import Field
from ema.core.workspace import Workspace

PROMPT_VERSION = "audit-draft-v2"
FACT_RULE = "Fiecare nume, număr şi dată vine dintr-un fapt, scris {{f:<key>}}."
REFERENCE_RULE = "Fiecare paragraf, celulă şi legendă enumeră fact_ids folosite."
WORDING_RULE = "Nu folosi formulări despre AI sau procesul de redactare."
SENTENCE_RULE = (
    "Fiecare propoziţie conţine cel puţin un {{f:<key>}}; nu scrie propoziţii fără fapt "
    "(introduceri, generalităţi, concluzii)."
)
LENGTH_RULE = (
    "Lungimea urmează faptele: un paragraf pentru fiecare subiect, iar un fapt care este "
    "un pasaj din sursă se scrie întreg, ca {{f:<key>}}, în paragraful lui."
)
INSTRUCTIONS = (
    "Redactează numai secţiunea cerută, în registrul auditorului. Fiecare nume, număr şi "
    "dată trebuie să provină dintr-un fapt şi să fie scris ca {{f:<key>}}. "
    f"{SENTENCE_RULE} {LENGTH_RULE} "
    "Nu folosi formulări despre AI sau procesul de redactare. "
    "Fiecare paragraf, celulă şi legendă enumeră fact_ids folosite. "
    "Dacă lipseşte un fapt necesar, foloseşte status missing."
)


def recorded_facts(ws: Workspace, job: str, section: str) -> dict[str, Field]:
    allowed = SECTION_FACTS[section]
    with ws.connect() as db:
        rows = db.execute("SELECT key,data FROM fields WHERE job_id=?", (job,))
        return {
            str(row["key"]): Field.model_validate_json(row["data"])
            for row in rows
            if fact_key(str(row["key"])) in allowed
        }


def draft_task(section: str) -> str:
    title = next(item.title for item in CATALOGUE if item.id == section)
    return (
        f"Redactează secţiunea {section} „{title}”. Câmpul section este exact „{section}”. "
        f"{FACT_RULE} {SENTENCE_RULE} {LENGTH_RULE} {REFERENCE_RULE} {WORDING_RULE}"
    )


def draft_content(
    ws: Workspace, section: str, facts: dict[str, Field], task: str | None = None
) -> str:
    guide = resource_path("audit", "prompts", "style_guide_v1.json").read_text(encoding="utf-8")
    return json.dumps(
        {
            "task": task or draft_task(section),
            "facts": [
                {
                    "key": key,
                    "value": str(field.value) if field.presence == "found" else None,
                    "presence": field.presence,
                    "unit": field.unit,
                }
                for key, field in sorted(facts.items())
            ],
            "style_guide": json.loads(guide),
            "style_example": configured_style_example(ws, section),
        },
        ensure_ascii=False,
    )


def draft_section_run(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    section: str,
    draft_provider: Provider,
    support_provider: Provider,
    *,
    model_id: str,
    support_model_id: str | None = None,
    facts: dict[str, Field] | None = None,
    synthetic: bool = False,
    client_live: bool = False,
    task: str | None = None,
) -> tuple[AgentState, SectionDraft, DraftCheck, tuple[DraftReview, ...]]:
    if section not in SECTION_FACTS:
        raise EmaError("section_missing", "Secţiunea de redactare lipseşte.", section)
    facts = recorded_facts(ws, job, section) if facts is None else facts
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
    content = draft_content(ws, section, facts, task)

    def read_draft(request: str) -> SectionDraft:
        result = complete_json(context, SectionDraft, INSTRUCTIONS, request, schema_retries=0)
        if result.section != section:
            raise EmaError("draft_section", "Secţiunea redactată nu corespunde.", section)
        return result

    draft = read_draft(content)
    check = check_draft(draft, facts, job)
    steps = 1
    if check.fatal:
        errors = [
            {
                "rule": issue.code,
                "rule_text": SENTENCE_RULE if issue.code == "uncited_sentence" else FACT_RULE,
                "location": issue.location,
                "detail": issue.detail,
            }
            for issue in check.fatal
        ]
        draft = read_draft(
            json.dumps(
                {"request": content, "rejected_draft": draft.model_dump(), "errors": errors},
                ensure_ascii=False,
            ),
        )
        steps = 2
        check = check_draft(draft, facts, job)
        if check.fatal:
            raise EmaError(
                "draft_incomplete",
                "Redactarea nu respectă regulile.",
                ", ".join(issue.code for issue in check.fatal),
            )
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
    try:
        flags = support_pass(support_context, draft, facts)
    except EmaError as exc:
        flags = (DraftReview("support_unavailable", "section", exc.code),)
    state = AgentState(
        messages=[],
        steps=steps,
        status="done",
        model_id=model_id,
        provider_name=draft_provider.name,
        prompt_version=PROMPT_VERSION,
    )
    return state, draft, check, flags


def draft_section_replay(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    section: str,
    draft_recording: Path,
    support_recording: Path,
    *,
    model_id: str | None = None,
    facts: dict[str, Field] | None = None,
) -> tuple[AgentState, SectionDraft, DraftCheck, tuple[DraftReview, ...]]:
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
        model_id=model_id or draft_provider.model_id,
        support_model_id=model_id or support_provider.model_id,
        facts=facts,
        synthetic=True,
    )
