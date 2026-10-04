"""One chapter call: a group's sections drafted together, checked, retried once, supported (D2).

The answer holds one draft per requested section. An unknown or repeated section is dropped and
logged, the first one kept; an omitted or failing one goes back once, with the passages and
opening sentences the accepted sections hold; still failing, it stays a marker.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ema.audit.catalogue_types import PASSAGE_FACTS, AuditFact, fact_key
from ema.audit.draft_checks import ANY_TOKEN, TOKEN, DraftCheck, DraftReview, check_draft
from ema.audit.draft_plan import Group, SectionPlan
from ema.audit.draft_prompt import (
    PROMPT_VERSION,
    SUPPORT_VERSION,
    Used,
    chapter_request,
    instructions,
    retry_request,
)
from ema.audit.draft_schema import ChapterDraft, SectionDraft
from ema.audit.draft_support import support_pass
from ema.core.errors import EmaError
from ema.core.llm import AgentContext, complete_json
from ema.core.llm.types import Provider
from ema.core.logging import write_event
from ema.core.review.models import Field
from ema.core.workspace import Workspace


@dataclass(frozen=True)
class Passes:
    draft: Provider
    support: Provider
    model_id: str
    support_model_id: str | None = None
    synthetic: bool = False
    client_live: bool = False


@dataclass(frozen=True)
class Drafted:
    draft: SectionDraft
    check: DraftCheck
    flags: tuple[DraftReview, ...]
    facts: dict[str, Field]


@dataclass(frozen=True)
class GroupResult:
    drafted: dict[str, Drafted] = field(default_factory=dict[str, Drafted])
    failed: dict[str, EmaError] = field(default_factory=dict[str, EmaError])


def unit_issues(
    draft: SectionDraft, plan: SectionPlan, units: Mapping[str, int | None]
) -> list[DraftReview]:
    """A ch3.process paragraph names its unit and cites only that unit's passages (D3)."""
    issues: list[DraftReview] = []
    count = len(plan.units)
    for index, item in enumerate(draft.paragraphs):
        location = f"paragraph:{index}"
        if draft.section != "ch3.process":
            if item.unit is not None:
                issues.append(DraftReview("unit_outside", location, str(item.unit)))
            continue
        if item.unit is None or not 1 <= item.unit <= count:
            issues.append(DraftReview("unit_missing", location, str(item.unit)))
            continue
        issues.extend(
            DraftReview("unit_passage", location, key)
            for key in ANY_TOKEN.findall(item.text)
            if fact_key(key) == AuditFact.PROCESS_SECTIONS and units.get(key) != item.unit
        )
    return issues


def rendered_passages(draft: SectionDraft) -> set[str]:
    return {
        key
        for item in draft.paragraphs
        for key in TOKEN.findall(item.text)
        if fact_key(key) in PASSAGE_FACTS
    }


def _picked(
    ws: Workspace, job: str, group: Group, answer: ChapterDraft, requested: Sequence[str]
) -> dict[str, SectionDraft]:
    """The first draft of each requested section; the rest is logged and dropped."""
    picked: dict[str, SectionDraft] = {}
    dropped: list[dict[str, str]] = [
        {"section": section, "reason": "malformed"} for section in answer.malformed
    ]
    for draft in answer.sections:
        if draft.section not in requested:
            dropped.append({"section": draft.section, "reason": "unknown"})
        elif draft.section in picked:
            dropped.append({"section": draft.section, "reason": "duplicate"})
        else:
            picked[draft.section] = draft
    if dropped:
        with ws.connect() as db, ws.job_log(db, job) as handle:
            write_event(handle, "draft_section_dropped", group=group.id, sections=dropped)
    return picked


def _sorted(
    drafts: Mapping[str, SectionDraft],
    requested: Sequence[str],
    plans: Mapping[str, SectionPlan],
    used: Used,
    units: Mapping[str, int | None],
    job: str,
) -> tuple[dict[str, tuple[SectionDraft, DraftCheck]], dict[str, list[DraftReview]]]:
    """Accepted drafts in catalogue order, each added to `used`; and each failing section's
    errors, an omitted one included."""
    accepted: dict[str, tuple[SectionDraft, DraftCheck]] = {}
    errors: dict[str, list[DraftReview]] = {}
    for section in requested:
        draft = drafts.get(section)
        if draft is None:
            errors[section] = [DraftReview("omitted", "section", section)]
            continue
        plan = plans[section]
        check = check_draft(draft, plan.facts, job)
        passages = rendered_passages(draft)
        issues = [
            *check.fatal,
            *unit_issues(draft, plan, units),
            *(
                DraftReview("passage_reused", "section", key)
                for key in sorted(passages & used.passages)
            ),
        ]
        if issues:
            errors[section] = issues
            continue
        accepted[section] = (draft, check)
        used.add(draft, passages, plan.facts)
    return accepted, errors


def run_group(
    ws: Workspace,
    job: str,
    group: Group,
    passes: Passes,
    used: Used,
    units: Mapping[str, int | None],
) -> GroupResult:
    """Draft the group in one call, retry its failing sections once, then check support once."""
    context = AgentContext(
        ws,
        job,
        f"draft:{group.id}",
        passes.draft,
        passes.model_id,
        PROMPT_VERSION,
        synthetic=passes.synthetic,
        client_live=passes.client_live,
    )
    plans = {plan.section: plan for plan in group.sections}
    requested = list(plans)

    def call(content: dict[str, object], sections: Sequence[str]) -> dict[str, SectionDraft]:
        answer = complete_json(
            context,
            ChapterDraft,
            instructions(),
            json.dumps(content, ensure_ascii=False),
            max_output_tokens=group.allowance,
            schema_retries=0,
        )
        return _picked(ws, job, group, answer, sections)

    try:
        drafts = call(chapter_request(group, used), requested)
    except EmaError as exc:
        if exc.code != "ai_schema":
            return GroupResult(failed=dict.fromkeys(requested, exc))
        # An answer that is not the schema, a truncated one too, omits every section.
        drafts = {}
    accepted, errors = _sorted(drafts, requested, plans, used, units, job)
    failed: dict[str, EmaError] = {}
    if errors:
        try:
            again = call(retry_request(group, used, drafts, errors), list(errors))
        except EmaError as exc:
            failed = dict.fromkeys(errors, exc)
        else:
            redrafted, errors = _sorted(again, list(errors), plans, used, units, job)
            accepted.update(redrafted)
            failed = {
                section: EmaError(
                    "draft_incomplete",
                    "Redactarea nu respectă regulile.",
                    ", ".join(sorted({issue.code for issue in issues})),
                )
                for section, issues in errors.items()
            }
    ordered = [accepted[section] for section in requested if section in accepted]
    facts = {key: value for plan in group.sections for key, value in plan.facts.items()}
    support_context = AgentContext(
        ws,
        job,
        f"support:{group.id}",
        passes.support,
        passes.support_model_id or passes.model_id,
        SUPPORT_VERSION,
        synthetic=passes.synthetic,
        client_live=passes.client_live,
    )
    flags = support_pass(support_context, [draft for draft, _ in ordered], facts)
    return GroupResult(
        {
            draft.section: Drafted(draft, check, flags[draft.section], plans[draft.section].facts)
            for draft, check in ordered
        },
        failed,
    )
