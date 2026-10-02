"""One audit section drafted as a job stage, from recorded facts and recorded AI responses."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ema.audit.draft_agent import PROMPT_VERSION
from ema.audit.draft_checks import DraftReview
from ema.audit.draft_live import live_provider
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.draft_write import (
    Drafted,
    live_passes,
    replay_passes,
    write_section,
)
from ema.audit.sections import get_status
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, get_job, run_stage, status, subscribe
from ema.core.llm import ReplayProvider
from ema.core.workspace import Workspace


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
    """Draft one chapter 2-3 section: by replay with both recordings, live with neither."""
    record = get_job(ws, job)
    if record["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    if record["state"] == "running":
        raise EmaError("job_running", "Lucrarea rulează deja.", job)
    if section not in SECTION_FACTS:
        raise EmaError("section_missing", "Secţiunea de redactare lipseşte.", section)
    if (draft_recording is None) != (support_recording is None):
        raise EmaError("replay_invalid", "Înregistrările AI sunt incomplete.", section)
    if draft_recording is not None and support_recording is not None:
        _replayable(draft_recording)
        _replayable(support_recording)
    drafted: list[Drafted] = []
    live = live_provider(ws) if draft_recording is None or support_recording is None else None

    def stage(ctx: StageContext) -> StageOutcome:
        if live is None:
            assert draft_recording is not None and support_recording is not None
            passes = replay_passes(draft_recording, support_recording)
        else:
            passes = live_passes(live[0], live[1], ctx.artifact_dir() / "draft", section)
        ctx.record_input(prompt=PROMPT_VERSION, model=passes.model_id)
        drafted.append(write_section(ctx, section, passes))
        return StageOutcome()

    run = run_stage(ws, job, "draft", stage)
    for _ in subscribe(ws, job):
        pass
    recorded = next(item for item in status(ws, job).runs if item["id"] == run)
    if recorded["state"] != "ready" or not drafted:
        raise EmaError("draft_failed", "Redactarea secţiunii a eşuat.", str(recorded["error"]))
    done = drafted[0]
    draft, check, directory = done.draft, done.check, done.directory
    return DraftResult(
        job=job,
        run=run,
        section=section,
        draft_status=draft.status,
        section_status=get_status(ws, job, section).status.value,
        coverage=check.coverage,
        cited_sentences=check.cited_sentences,
        total_sentences=check.total_sentences,
        review=(*check.review, *done.review),
        draft_path=directory / f"{section}.json",
        review_path=directory / f"{section}.draft-review.json",
    )
