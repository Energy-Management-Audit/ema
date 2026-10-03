"""One section drafted inside a running Draft stage: both passes, artifacts, and the queue."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ema.audit.draft_agent import draft_section_run, draft_task, recorded_facts
from ema.audit.draft_checks import DraftCheck, DraftReview
from ema.audit.draft_render import review_payload
from ema.audit.draft_schema import SECTION_FACTS, SectionDraft
from ema.audit.publication import queue_sections
from ema.audit.sections import recompute_ready
from ema.core.jobs import StageContext
from ema.core.llm import RecordingProvider, ReplayProvider
from ema.core.llm.types import Provider


@dataclass(frozen=True)
class Passes:
    draft: Provider
    support: Provider
    model_id: str
    support_model_id: str | None = None
    synthetic: bool = False
    client_live: bool = False
    task: str | None = None


@dataclass(frozen=True)
class Drafted:
    draft: SectionDraft
    check: DraftCheck
    review: tuple[DraftReview, ...]
    directory: Path


def replay_passes(draft: Path, support: Path) -> Passes:
    draft_provider, support_provider = ReplayProvider(draft), ReplayProvider(support)
    return Passes(
        draft_provider,
        support_provider,
        draft_provider.model_id,
        support_provider.model_id,
        synthetic=True,
    )


def live_passes(provider: Provider, model_id: str, directory: Path, section: str) -> Passes:
    return Passes(
        RecordingProvider(provider, directory / f"{section}.draft.json"),
        RecordingProvider(provider, directory / f"{section}.support.json"),
        model_id,
        client_live=True,
        task=draft_task(section),
    )


def write_section(ctx: StageContext, section: str, passes: Passes) -> Drafted:
    facts = recorded_facts(ctx.ws, ctx.job, section)
    for field in facts.values():
        ctx.record_read("fields", field.id, field.revision)
    _, draft, check, flags = draft_section_run(
        ctx.ws,
        ctx.job,
        section,
        passes.draft,
        passes.support,
        model_id=passes.model_id,
        support_model_id=passes.support_model_id,
        facts=facts,
        synthetic=passes.synthetic,
        client_live=passes.client_live,
        task=passes.task,
    )
    directory = ctx.artifact_dir() / "sections"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{section}.json").write_text(draft.model_dump_json(indent=2), "utf-8")
    (directory / f"{section}.draft-review.json").write_text(
        json.dumps(review_payload(draft, check, flags), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if draft.status == "drafted":
        recompute_ready(ctx.ws, ctx.job)
        queue_sections(
            ctx,
            (section,),
            "agent",
            tuple(f"fact:{key}" for key in SECTION_FACTS[section]),
            facts=facts,
        )
    return Drafted(draft, check, flags, directory)
