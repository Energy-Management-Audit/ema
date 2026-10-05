"""The Draft stage over a live model: chapters 2 and 3, one call per chapter group (D2)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ema.audit.catalogue import CATALOGUE
from ema.audit.draft_agent import chapter_groups, job_facts
from ema.audit.draft_chapter import run_group
from ema.audit.draft_plan import usable
from ema.audit.draft_prompt import PROMPT_VERSION, Used
from ema.audit.draft_schema import SECTION_FACTS, citable
from ema.audit.draft_write import live_passes, write_section
from ema.audit.fill_stage import (
    STOPPING,
    log_spend,
    provider_failure,
    settings_provider,
    stopped_warning,
)
from ema.audit.sections import get_status, recompute_ready
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, run_stage
from ema.core.llm.agent import job_spend
from ema.core.llm.types import Provider
from ema.core.logging import write_event
from ema.core.review.section_transition import Status
from ema.core.workspace import Workspace


@dataclass(frozen=True)
class DraftSummary:
    run: str
    drafted: dict[str, str] = field(default_factory=dict[str, str])
    failed: dict[str, str] = field(default_factory=dict[str, str])
    skipped: tuple[str, ...] = ()
    not_applicable: tuple[str, ...] = ()
    stopped: tuple[str, ...] = ()


def live_provider(ws: Workspace) -> tuple[Provider, str]:
    """The Settings provider and model; refuses before any run when the live switch is off."""
    settings = load_settings(ws)
    if not settings.ai_client_live:
        raise EmaError("ai_client_disabled", "Documentele clientului nu pot fi trimise la AI.", "")
    return settings_provider(settings)


def failure_code(exc: EmaError) -> str:
    # run_agent wraps provider refusals as ai_provider and keeps the original code in detail.
    return exc.detail if exc.code == "ai_provider" and exc.detail.startswith("ai_") else exc.code


def draftable(ws: Workspace, job: str) -> tuple[list[str], list[str], list[str]]:
    """Chapter 2-3 section ids split into (to draft, no found fact, not applicable)."""
    ready: list[str] = []
    empty: list[str] = []
    absent: list[str] = []
    facts = job_facts(ws, job)
    for section in CATALOGUE:
        if section.id not in SECTION_FACTS:
            continue
        state = get_status(ws, job, section.id)
        if state.applicability is False or state.status == Status.NA:
            absent.append(section.id)
        elif any(usable(value) for key, value in facts.items() if citable(section.id, key)):
            ready.append(section.id)
        else:
            empty.append(section.id)
    return ready, empty, absent


def _draft_all(
    ctx: StageContext,
    provider: Provider,
    model_id: str,
    sections: list[str],
    skipped: list[str],
    absent: list[str],
) -> DraftSummary:
    """One call per chapter group, chapter 3 first and in catalogue order within a chapter;
    a quota or the budget stops the rest."""
    drafted: dict[str, str] = {}
    failed: dict[str, str] = {}
    ctx.record_input(prompt=PROMPT_VERSION, model=model_id)
    facts = job_facts(ctx.ws, ctx.job)
    recompute_ready(ctx.ws, ctx.job)
    groups, units = chapter_groups(ctx.ws, ctx.job, sections, facts)
    # Chapter 3 first: budget spent on chapter 2 retries no longer leaves it undrafted (#137).
    groups = sorted(groups, key=lambda group: -group.chapter)
    used = {2: Used(), 3: Used()}
    stopped: tuple[str, ...] = ()
    for index, group in enumerate(groups):
        passes = live_passes(provider, model_id, ctx.artifact_dir(), group.id)
        result = run_group(ctx.ws, ctx.job, group, passes, used[group.chapter], units)
        for section, done in result.drafted.items():
            write_section(ctx, done, ready=True, facts=facts)
            drafted[section] = done.draft.status
        for section, exc in result.failed.items():
            failed[section] = failure_code(exc)
            with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
                write_event(
                    handle,
                    "draft_failed",
                    run=ctx.run_id,
                    section=section,
                    code=failed[section],
                    detail=exc.detail,
                    **provider_failure(exc),
                )
        if any(failed[section] in STOPPING for section in result.failed):
            stopped = tuple(
                plan.section for later in groups[index + 1 :] for plan in later.sections
            )
            break
    return DraftSummary(ctx.run_id, drafted, failed, tuple(skipped), tuple(absent), stopped)


def start_draft(
    ws: Workspace,
    job: str,
    *,
    on_revision: int | None = None,
    summaries: list[DraftSummary] | None = None,
) -> str:
    provider, model_id = live_provider(ws)
    sections, skipped, absent = draftable(ws, job)

    def stage(ctx: StageContext) -> StageOutcome:
        before = job_spend(ctx.ws, ctx.job)
        try:
            summary = _draft_all(ctx, provider, model_id, sections, skipped, absent)
        finally:
            log_spend(ctx, "draft", before)
        if summaries is not None:
            summaries.append(summary)
        return StageOutcome(
            item_failures=[f"{key}: {code}" for key, code in summary.failed.items()],
            warnings=stopped_warning(summary.failed, summary.stopped),
        )

    return run_stage(ws, job, "draft", stage, on_revision=on_revision)
