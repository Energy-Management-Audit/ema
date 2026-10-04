"""One audit section drafted as a job stage, from recorded facts and recorded AI responses."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ema.audit.draft_agent import draft_one
from ema.audit.draft_chapter import Drafted, Passes
from ema.audit.draft_checks import DraftReview
from ema.audit.draft_live import live_provider
from ema.audit.draft_prompt import PROMPT_VERSION
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.draft_write import chapter_replay, live_passes, replay_passes, write_section
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


def _passes(
    ws: Workspace,
    section: str,
    draft_recording: Path | None,
    support_recording: Path | None,
    recording: Path | None,
) -> Callable[[Path], Passes]:
    """The stage's passes from its artifact folder: checked recordings, or the live provider,
    refused before any run when the live switch is off."""
    if (draft_recording is None) != (support_recording is None):
        raise EmaError("replay_invalid", "Înregistrările AI sunt incomplete.", section)
    if recording is not None and draft_recording is not None:
        raise EmaError("replay_invalid", "Înregistrările AI sunt în conflict.", section)
    if recording is not None:
        _replayable(recording)
        return lambda _: chapter_replay(recording)
    if draft_recording is not None and support_recording is not None:
        _replayable(draft_recording)
        _replayable(support_recording)
        return lambda _: replay_passes(draft_recording, support_recording)
    provider, model_id = live_provider(ws)
    return lambda directory: live_passes(provider, model_id, directory, section)


def draft_section(
    ws: Workspace,
    job: str,
    section: str,
    *,
    draft_recording: Path | None = None,
    support_recording: Path | None = None,
    recording: Path | None = None,
) -> DraftResult:
    """Draft one chapter 2-3 section through the chapter path: by replay with both recordings
    or with the chapter-<section> recording a live run wrote, live with none."""
    record = get_job(ws, job)
    if record["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    if record["state"] == "running":
        raise EmaError("job_running", "Lucrarea rulează deja.", job)
    if section not in SECTION_FACTS:
        raise EmaError("section_missing", "Secţiunea de redactare lipseşte.", section)
    source = _passes(ws, section, draft_recording, support_recording, recording)
    drafted: list[tuple[Drafted, Path]] = []

    def stage(ctx: StageContext) -> StageOutcome:
        passes = source(ctx.artifact_dir())
        ctx.record_input(prompt=PROMPT_VERSION, model=passes.model_id)
        done = draft_one(ctx.ws, ctx.job, section, passes)
        drafted.append((done, write_section(ctx, done)))
        return StageOutcome()

    run = run_stage(ws, job, "draft", stage)
    for _ in subscribe(ws, job):
        pass
    recorded = next(item for item in status(ws, job).runs if item["id"] == run)
    if recorded["state"] != "ready" or not drafted:
        raise EmaError("draft_failed", "Redactarea secţiunii a eşuat.", str(recorded["error"]))
    done, directory = drafted[0]
    draft, check = done.draft, done.check
    return DraftResult(
        job=job,
        run=run,
        section=section,
        draft_status=draft.status,
        section_status=get_status(ws, job, section).status.value,
        coverage=check.coverage,
        cited_sentences=check.cited_sentences,
        total_sentences=check.total_sentences,
        review=(*check.review, *done.flags),
        draft_path=directory / f"{section}.json",
        review_path=directory / f"{section}.draft-review.json",
    )
