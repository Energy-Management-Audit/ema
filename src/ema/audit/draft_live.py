"""The Draft stage over a live model: every chapter 2-3 section that has recorded facts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from ema.audit.catalogue import CATALOGUE
from ema.audit.draft_agent import PROMPT_VERSION, recorded_facts
from ema.audit.draft_schema import SECTION_FACTS
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
    for section in CATALOGUE:
        if section.id not in SECTION_FACTS:
            continue
        state = get_status(ws, job, section.id)
        if state.applicability is False or state.status == Status.NA:
            absent.append(section.id)
        elif any(f.presence == "found" for f in recorded_facts(ws, job, section.id).values()):
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
    drafted: dict[str, str] = {}
    failed: dict[str, str] = {}
    directory = ctx.artifact_dir() / "draft"
    ctx.record_input(prompt=PROMPT_VERSION, model=model_id)
    recompute_ready(ctx.ws, ctx.job)

    def run_one(section: str) -> tuple[str, str, dict[str, str | int] | None]:
        try:
            result = write_section(
                ctx, section, live_passes(provider, model_id, directory, section), ready=True
            )
            return section, result.draft.status, None
        except EmaError as exc:
            return section, failure_code(exc), provider_failure(exc)

    stopped: tuple[str, ...] = ()
    with ThreadPoolExecutor(max_workers=4) as pool:
        for offset in range(0, len(sections), 4):
            batch = sections[offset : offset + 4]
            results = list(pool.map(run_one, batch))
            for section, value, cause in results:
                if cause is None:
                    drafted[section] = value
                    continue
                failed[section] = value
                with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
                    write_event(
                        handle, "draft_failed", run=ctx.run_id, section=section, code=value, **cause
                    )
            if any(value in STOPPING for _, value, cause in results if cause is not None):
                stopped = tuple(sections[offset + len(batch) :])
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
