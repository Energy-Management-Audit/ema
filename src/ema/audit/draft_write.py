"""A drafted section inside a running Draft stage: its artifacts, reads and review queue entry."""

from __future__ import annotations

import json
from pathlib import Path

from ema.audit.draft_chapter import Drafted, Passes
from ema.audit.draft_render import review_payload
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.publication import queue_sections
from ema.audit.sections import recompute_ready
from ema.core.jobs import StageContext
from ema.core.llm import RecordingProvider, ReplayProvider
from ema.core.llm.types import Provider


def replay_passes(draft: Path, support: Path) -> Passes:
    draft_provider, support_provider = ReplayProvider(draft), ReplayProvider(support)
    return Passes(
        draft_provider,
        support_provider,
        draft_provider.model_id,
        support_provider.model_id,
        synthetic=True,
    )


def live_passes(provider: Provider, model_id: str, directory: Path, group: str) -> Passes:
    """Both passes of a chapter group recorded, in call order, in draft/<run>/chapter-<group>."""
    recording = RecordingProvider(provider, directory / f"chapter-{group}.json")
    return Passes(recording, recording, model_id, client_live=True)


def write_section(ctx: StageContext, done: Drafted, *, ready: bool = False) -> Path:
    """Write sections/<section>.json and its review beside it; queue a drafted section."""
    section = done.draft.section
    for field in done.facts.values():
        ctx.record_read("fields", field.id, field.revision)
    directory = ctx.artifact_dir() / "sections"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{section}.json").write_text(done.draft.model_dump_json(indent=2), "utf-8")
    (directory / f"{section}.draft-review.json").write_text(
        json.dumps(
            review_payload(done.draft, done.check, done.flags), ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    if done.draft.status == "drafted":
        if not ready:
            recompute_ready(ctx.ws, ctx.job)
        keys = {*SECTION_FACTS[section], *done.facts}
        queue_sections(
            ctx,
            (section,),
            "agent",
            tuple(f"fact:{key}" for key in sorted(keys)),
            facts=done.facts,
        )
    return directory
