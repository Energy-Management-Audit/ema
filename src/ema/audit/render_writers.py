"""The chapter writers of the full audit render: each reads the previous file, writes the next."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from collections.abc import Callable
from functools import partial
from pathlib import Path

from pydantic import BaseModel

from ema.audit.chapter_five import ChapterFivePlan
from ema.audit.chapter_five_render import render_chapter_five
from ema.audit.chapter_four import render_chapter_four
from ema.audit.chapter_four_blocks import _written
from ema.audit.chapter_four_sentences import sentence_plan, write_sentence_record
from ema.audit.chapter_six import ChapterSixPlan, render_chapter_six
from ema.audit.chapter_tables import write_charts, write_tables
from ema.audit.draft_checks import DraftReview
from ema.audit.draft_render import render_section
from ema.audit.draft_schema import SectionDraft, citable
from ema.audit.intake import select_checklist
from ema.audit.read import NARRATIVE_SECTIONS
from ema.audit.render_dataset import reviewed_dataset
from ema.audit.section_body import replace_section_body
from ema.core.errors import EmaError
from ema.core.jobs import StageContext
from ema.core.jobs.reads import run_current
from ema.core.review.models import Field
from ema.core.workspace import SlotVersion, Workspace
from ema.energy_data.factors import AUDIT_FACTORS_2026
from ema.energy_data.necesar import parse_necesar_info, to_dataset


class RenderFailure(BaseModel):
    section_id: str
    code: str


class Chain:
    """Each writer reads the previous file and writes a new one; a failed writer is skipped."""

    def __init__(self, folder: Path, start: Path) -> None:
        self.folder, self.current, self.step = folder, start, 0
        self.failures: list[RenderFailure] = []

    def apply(self, section_id: str, write: Callable[[Path, Path], object]) -> bool:
        self.step += 1
        target = self.folder / f"{self.step:02d}-{section_id}.docx"
        try:
            write(self.current, target)
        except Exception as exc:  # one failed section never fails the render (R21)
            code = exc.code if isinstance(exc, EmaError) else type(exc).__name__
            self.failures.append(RenderFailure(section_id=section_id, code=code))
            target.unlink(missing_ok=True)
            return False
        self.current = target
        return True


def text_of(by_key: dict[str, Field], key: str) -> str | None:
    """A text the auditor wrote: its value unless she rejected it."""
    field = by_key.get(key)
    if field is None or field.value is None or field.review == "rejected":
        return None
    return str(field.value)


def ready_runs(
    ws: Workspace, job: str, stage: str, *, ctx: StageContext | None = None
) -> list[Path]:
    """Artifact folders of the stage's ready runs, newest first."""
    with ws.connect() as db:
        rows = db.execute(
            "SELECT id FROM runs WHERE job_id=? AND stage=? AND state='ready' "
            "ORDER BY ended_at DESC",
            (job, stage),
        ).fetchall()
        current: list[Path] = []
        for index, row in enumerate(rows):
            run = str(row["id"])
            if not run_current(db, run):
                if index == 0:
                    raise EmaError(
                        "output_stale",
                        "Planul capitolului s-a modificat. Refaceţi compunerea.",
                        stage,
                    )
                continue
            if ctx is not None:
                for read in db.execute(
                    "SELECT table_name,row_id,revision FROM run_reads WHERE run_id=?", (run,)
                ):
                    ctx.record_read(read["table_name"], read["row_id"], read["revision"])
            current.append(ws.artifact_dir(db, job, stage, run))
        return current


def _draft(
    ws: Workspace, job: str, section: str, ctx: StageContext | None = None
) -> tuple[SectionDraft, tuple[DraftReview, ...]]:
    folder = next(
        item / "sections"
        for item in ready_runs(ws, job, "draft", ctx=ctx)
        if (item / "sections" / f"{section}.json").is_file()
    )
    draft = SectionDraft.model_validate_json(
        (folder / f"{section}.json").read_text(encoding="utf-8")
    )
    review = folder / f"{section}.draft-review.json"
    items: list[dict[str, str | None]] = (
        json.loads(review.read_text(encoding="utf-8"))["review"] if review.is_file() else []
    )
    return draft, review_flags(items)


def review_flags(items: list[dict[str, str | None]]) -> tuple[DraftReview, ...]:
    """The stored review, with the flagged sentence the render marks in place of its paragraph."""
    return tuple(
        DraftReview(
            str(item["code"]), str(item["location"]), str(item["detail"]), item.get("sentence")
        )
        for item in items
    )


def section_facts(section: str, by_key: dict[str, Field]) -> dict[str, Field]:
    """The facts a section's draft may cite, numbered passages of its narrative facts included."""
    return {key: field for key, field in by_key.items() if citable(section, key)}


def drafted_sections(ws: Workspace, job: str, *, ctx: StageContext | None = None) -> set[str]:
    return {
        path.stem
        for folder in ready_runs(ws, job, "draft", ctx=ctx)
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
    by_key: dict[str, Field],
    ctx: StageContext | None = None,
) -> None:
    draft, flags = _draft(ws, job, section, ctx)
    render_section(source, target, draft, section_facts(section, by_key), flags, job=job)


def write_chapter_tables(
    chain: Chain, chapter_id: str, fields: list[Field], chart_source: Path
) -> None:
    """The Necesar-info tables of ch. 2 or ch. 3, then ch. 2's charts: two steps, two failures."""
    chain.apply(
        f"{chapter_id}.tables",
        partial(write_tables, chapter=chapter_id, fields=fields),
    )
    if chapter_id == "ch2":
        chain.apply("ch2.charts", partial(write_charts, fields=fields, chart_source=chart_source))


def write_intro(source: Path, target: Path, *, section_id: str, text: str | None) -> None:
    """A chapter's introduction as she wrote it, over the chapter's own region."""
    replace_section_body(source, target, section_id, _written(text))


def write_four(  # noqa: PLR0913
    source: Path,
    target: Path,
    *,
    ws: Workspace,
    client: str,
    dossier: list[SlotVersion],
    job_fields: list[Field],
    identity: tuple[str, ...],
    chart_source: Path,
    client_name: str,
    charts_skipped: list[str],
) -> None:
    checklist = select_checklist(dossier)
    parsed = to_dataset(parse_necesar_info(ws.file_path(client, checklist.file_sha)))
    dataset = reviewed_dataset(parsed, job_fields)
    if not dataset.carriers or not dataset.years:
        raise EmaError("ch4_no_data", "Capitolul 4 nu are date de consum.", "")
    by_key = {field.key: field for field in job_fields}
    texts = {
        section_id: text
        for section_id in NARRATIVE_SECTIONS
        if (text := text_of(by_key, f"narrative.{section_id}")) is not None
    }
    _, skipped = render_chapter_four(
        source,
        target,
        dataset,
        identity,
        chart_source=chart_source,
        client=client_name,
        texts=texts,
    )
    write_sentence_record(
        target.parent / "ch4-sentences.json", sentence_plan(dataset, AUDIT_FACTORS_2026)
    )
    charts_skipped.extend(skipped)


def write_five(
    run: Path, images: dict[str, Path], identity: tuple[str, ...], source: Path, target: Path
) -> None:
    plan = ChapterFivePlan.model_validate_json(
        (run / "sections" / "ch5.json").read_text(encoding="utf-8")
    )
    render_chapter_five(source, target, plan, images, identity)


def write_six(run: Path, identity: tuple[str, ...], source: Path, target: Path) -> None:
    plan = ChapterSixPlan.model_validate_json(
        (run / "sections" / "ch6.json").read_text(encoding="utf-8")
    )
    render_chapter_six(source, target, plan, identity)
