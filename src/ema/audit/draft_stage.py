"""One audit section drafted as a job stage, from recorded facts and recorded AI responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ema.audit.draft_agent import (
    PROMPT_VERSION,
    REPLAY_MODEL,
    draft_section_live,
    draft_section_replay,
    recorded_facts,
)
from ema.audit.draft_checks import DraftCheck, DraftReview
from ema.audit.draft_render import review_payload
from ema.audit.draft_schema import SECTION_FACTS, SectionDraft
from ema.audit.publication import queue_sections
from ema.audit.sections import get_status, recompute_ready
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, get_job, run_stage, status, subscribe
from ema.core.llm import Limits, ReplayProvider
from ema.core.workspace import Workspace

DRAFT_STEPS = 8


@dataclass(frozen=True)
class DraftResult:
    job: str
    run: str
    section: str
    draft_status: Literal["drafted", "missing"]
    section_status: str
    coverage: float
    cited_sentences: int
    total_sentences: int
    review: tuple[DraftReview, ...]
    draft_path: Path
    review_path: Path


def _replayable(recording: Path) -> None:
    """Construct the provider once to reject a broken recording before any run starts."""
    try:
        ReplayProvider(recording)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise EmaError(
            "replay_invalid", "Înregistrarea AI este invalidă.", f"{recording.name}: {exc}"
        ) from exc


def draft_section(
    ws: Workspace,
    job: str,
    section: str,
    *,
    draft_recording: Path | None,
    support_recording: Path | None,
) -> DraftResult:
    """Draft one chapter 2-3 section by replay; live AI drafting stays disabled."""
    record = get_job(ws, job)
    if record["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    if record["state"] == "running":
        raise EmaError("job_running", "Lucrarea rulează deja.", job)
    if section not in SECTION_FACTS:
        raise EmaError("section_missing", "Secţiunea de redactare lipseşte.", section)
    if draft_recording is None or support_recording is None:
        draft_section_live()
    _replayable(draft_recording)
    _replayable(support_recording)
    drafted: list[tuple[SectionDraft, DraftCheck, tuple[DraftReview, ...], Path]] = []

    def stage(ctx: StageContext) -> StageOutcome:
        composition_facts = recorded_facts(ws, job, section)
        for field in composition_facts.values():
            ctx.record_read("fields", field.id, field.revision)
        ctx.record_input(prompt=PROMPT_VERSION, model=REPLAY_MODEL)
        _, draft, check, flags = draft_section_replay(
            ws,
            job,
            section,
            draft_recording,
            support_recording,
            Limits(DRAFT_STEPS),
            facts=composition_facts,
        )
        directory = ctx.artifact_dir() / "sections"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{section}.json").write_text(draft.model_dump_json(indent=2), "utf-8")
        (directory / f"{section}.draft-review.json").write_text(
            json.dumps(review_payload(draft, check, flags), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if draft.status == "drafted":
            recompute_ready(ws, job)
            queue_sections(
                ctx,
                (section,),
                "agent",
                tuple(f"fact:{key}" for key in SECTION_FACTS[section]),
                facts=composition_facts,
            )
        drafted.append((draft, check, flags, directory))
        return StageOutcome()

    run = run_stage(ws, job, "draft", stage)
    for _ in subscribe(ws, job):
        pass
    recorded = next(item for item in status(ws, job).runs if item["id"] == run)
    if recorded["state"] != "ready" or not drafted:
        raise EmaError("draft_failed", "Redactarea secţiunii a eşuat.", str(recorded["error"]))
    draft, check, flags, directory = drafted[0]
    return DraftResult(
        job=job,
        run=run,
        section=section,
        draft_status=draft.status,
        section_status=get_status(ws, job, section).status.value,
        coverage=check.coverage,
        cited_sentences=check.cited_sentences,
        total_sentences=check.total_sentences,
        review=(*check.review, *flags),
        draft_path=directory / f"{section}.json",
        review_path=directory / f"{section}.draft-review.json",
    )
