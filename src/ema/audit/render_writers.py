"""The chapter writers of the full audit render: each reads the previous file, writes the next."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from ema.audit.chapter_five import ChapterFivePlan
from ema.audit.chapter_five_render import render_chapter_five
from ema.audit.chapter_four import render_chapter_four
from ema.audit.chapter_six import ChapterSixPlan, render_chapter_six
from ema.audit.draft_checks import DraftReview
from ema.audit.draft_render import render_section
from ema.audit.draft_schema import SECTION_FACTS, SectionDraft
from ema.audit.intake import select_checklist
from ema.audit.read import NARRATIVE_SECTIONS
from ema.audit.render_dataset import reviewed_dataset
from ema.core.review.models import Field
from ema.core.workspace import SlotVersion, Workspace
from ema.energy_data.necesar import parse_necesar_info, to_dataset


def ready_runs(ws: Workspace, job: str, stage: str) -> list[Path]:
    """Artifact folders of the stage's ready runs, newest first."""
    with ws.connect() as db:
        rows = db.execute(
            "SELECT id FROM runs WHERE job_id=? AND stage=? AND state='ready' "
            "ORDER BY ended_at DESC",
            (job, stage),
        ).fetchall()
        return [ws.artifact_dir(db, job, stage, str(row["id"])) for row in rows]


def _draft(ws: Workspace, job: str, section: str) -> tuple[SectionDraft, tuple[DraftReview, ...]]:
    folder = next(
        item / "sections"
        for item in ready_runs(ws, job, "draft")
        if (item / "sections" / f"{section}.json").is_file()
    )
    draft = SectionDraft.model_validate_json((folder / f"{section}.json").read_text("utf-8"))
    review = folder / f"{section}.draft-review.json"
    items: list[dict[str, str]] = (
        json.loads(review.read_text("utf-8"))["review"] if review.is_file() else []
    )
    return draft, tuple(
        DraftReview(item["code"], item["location"], item["detail"]) for item in items
    )


def drafted_sections(ws: Workspace, job: str) -> set[str]:
    return {
        path.stem
        for folder in ready_runs(ws, job, "draft")
        for path in (folder / "sections").glob("*.json")
        if not path.name.endswith(".draft-review.json")
    }


def write_draft(  # noqa: PLR0913
    source: Path,
    target: Path,
    *,
    ws: Workspace,
    job: str,
    section: str,
    anchors: Path,
    by_key: dict[str, Field],
) -> None:
    draft, flags = _draft(ws, job, section)
    facts = {key: by_key[key] for key in SECTION_FACTS.get(section, ()) if key in by_key}
    render_section(source, anchors, target, draft, facts, flags, job=job)


def write_four(  # noqa: PLR0913
    source: Path,
    target: Path,
    *,
    ws: Workspace,
    client: str,
    dossier: list[SlotVersion],
    job_fields: list[Field],
    identity: tuple[str, ...],
) -> None:
    checklist = select_checklist(dossier)
    parsed = to_dataset(parse_necesar_info(ws.file_path(client, checklist.file_sha)))
    dataset = reviewed_dataset(parsed, job_fields)
    if not dataset.carriers or not dataset.years:
        shutil.copyfile(source, target)
        return
    by_key = {field.key: field for field in job_fields}
    texts = {
        section_id: str(field.value)
        for section_id in NARRATIVE_SECTIONS
        if (field := by_key.get(f"narrative.{section_id}")) is not None
        and field.value is not None
        and field.review != "rejected"
    }
    render_chapter_four(source, target, dataset, identity, texts=texts)


def write_five(
    run: Path, images: dict[str, Path], identity: tuple[str, ...], source: Path, target: Path
) -> None:
    plan = ChapterFivePlan.model_validate_json((run / "sections" / "ch5.json").read_text("utf-8"))
    render_chapter_five(source, target, plan, images, identity)


def write_six(run: Path, identity: tuple[str, ...], source: Path, target: Path) -> None:
    plan = ChapterSixPlan.model_validate_json((run / "sections" / "ch6.json").read_text("utf-8"))
    render_chapter_six(source, target, plan, identity)
