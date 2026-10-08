"""The chapter groups of a Draft run, and one section drafted by the same chapter path."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from ema.audit.catalogue import CATALOGUE
from ema.audit.draft_chapter import Drafted, Passes, run_group
from ema.audit.draft_checks import DraftCheck, DraftReview
from ema.audit.draft_plan import Group, plan_section, split
from ema.audit.draft_prompt import PROMPT_VERSION, Used
from ema.audit.draft_schema import SECTION_FACTS, SectionDraft, citable
from ema.audit.draft_style import reference_examples
from ema.audit.process_units import ProcessUnits, job_process_units, passage_units
from ema.core.errors import EmaError
from ema.core.llm import ReplayProvider
from ema.core.llm.agent import AgentState
from ema.core.llm.types import Provider
from ema.core.logging import write_event
from ema.core.review.models import Field
from ema.core.workspace import Workspace

_CHAPTERS = {section.id: section.chapter for section in CATALOGUE}


def job_facts(ws: Workspace, job: str) -> dict[str, Field]:
    with ws.connect() as db:
        rows = db.execute("SELECT key,data FROM fields WHERE job_id=?", (job,))
        return {str(row["key"]): Field.model_validate_json(row["data"]) for row in rows}


def recorded_facts(ws: Workspace, job: str, section: str) -> dict[str, Field]:
    return {key: value for key, value in job_facts(ws, job).items() if citable(section, key)}


def _units(ws: Workspace, job: str) -> tuple[dict[str, int | None], int]:
    """Each process passage's 3.1.x unit and the unit count; an unreadable dossier gives one
    unit and leaves every passage to the overview."""
    try:
        units = job_process_units(ws, job)
        return passage_units(ws, job, units), units.count
    except Exception as exc:  # The Fişa is a client file: one that will not open is logged.
        with ws.connect() as db, ws.job_log(db, job) as handle:
            write_event(handle, "draft_units_failed", error=type(exc).__name__)
        return {}, ProcessUnits().count


def chapter_groups(
    ws: Workspace,
    job: str,
    sections: Sequence[str],
    facts: dict[str, Field] | None = None,
) -> tuple[list[Group], dict[str, int | None]]:
    """The sections' chapter groups in catalogue order, with each process passage's unit."""
    facts = job_facts(ws, job) if facts is None else facts
    examples = reference_examples(ws, job, sections)
    units, count = _units(ws, job) if {"ch3.flux", "ch3.process"} & set(sections) else ({}, 1)
    groups: list[Group] = []
    for chapter in (2, 3):
        plans = [
            plan_section(
                section,
                {key: value for key, value in facts.items() if citable(section, key)},
                examples.get(section),
                units,
                count,
            )
            for section in sections
            if _CHAPTERS[section] == chapter
        ]
        if plans:
            groups.extend(split(chapter, plans))
    return groups, units


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
) -> tuple[AgentState, SectionDraft, DraftCheck, tuple[DraftReview, ...]]:
    """One section through the chapter path, restricted to it: one group of one section."""
    if section not in SECTION_FACTS:
        raise EmaError("section_missing", "Secţiunea de redactare lipseşte.", section)
    passes = Passes(
        draft_provider,
        support_provider,
        model_id,
        support_model_id,
        synthetic=synthetic,
        client_live=client_live,
    )
    done = draft_one(ws, job, section, passes, facts)
    state = AgentState(
        messages=[],
        steps=1,
        status="done",
        model_id=model_id,
        provider_name=passes.draft.name,
        prompt_version=PROMPT_VERSION,
    )
    return state, done.draft, done.check, done.flags


def draft_one(
    ws: Workspace, job: str, section: str, passes: Passes, facts: dict[str, Field] | None = None
) -> Drafted:
    (group,), units = chapter_groups(ws, job, (section,), facts)
    group = Group(section, group.chapter, group.sections)
    result = run_group(ws, job, group, passes, Used(), units)
    if section in result.failed:
        raise result.failed[section]
    return result.drafted[section]


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
