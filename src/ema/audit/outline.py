"""One coherent read of the audit catalogue, section state, and human annotations."""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from ema.audit.applicability import fact_fields
from ema.audit.catalogue import CATALOGUE
from ema.audit.sections import _computed  # pyright: ignore[reportPrivateUsage]
from ema.core.errors import EmaError
from ema.core.review.models import Field
from ema.core.review.section_transition import SectionState
from ema.core.workspace import Workspace


class Annotation(BaseModel):
    text: str
    revision: int


class Deadline(BaseModel):
    value: str | None
    revision: int


class OutlineNode(BaseModel):
    id: str
    parent: str | None
    chapter: int
    number: str
    title: str
    kind: str
    status: str
    computed_status: str
    stale: bool
    reason: str | None
    changed_input: str | None
    applicability_reason: str | None
    awaits: list[str]
    missing_facts: list[str]
    revision: int
    note: Annotation | None
    answered: bool


class AuditOutline(BaseModel):
    nodes: list[OutlineNode]
    deadline: Deadline
    visit_date: str | None
    answered: int
    total: int
    written: int
    chapters: int


def outline(ws: Workspace, job: str) -> AuditOutline:
    with ws.connect() as db:
        db.execute("BEGIN")
        owner = db.execute("SELECT type FROM jobs WHERE id=? AND deleted=0", (job,)).fetchone()
        if owner is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        if owner["type"] != "audit":
            raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
        state_rows = db.execute(
            "SELECT section_id,data FROM section_states WHERE job_id=?", (job,)
        ).fetchall()
        field_rows = db.execute("SELECT data FROM fields WHERE job_id=?", (job,)).fetchall()
        material_rows = db.execute(
            "SELECT kind,present FROM audit_materials WHERE job_id=?", (job,)
        ).fetchall()
        annotation_rows = db.execute(
            "SELECT key,value,revision FROM job_annotations WHERE job_id=?", (job,)
        ).fetchall()
    states = {str(row["section_id"]): SectionState.parse(row["data"]) for row in state_rows}
    fields = {
        field.key: field for row in field_rows if (field := Field.model_validate_json(row["data"]))
    }
    materials = {str(row["kind"]): bool(row["present"]) for row in material_rows}
    notes = {str(row["key"]): row for row in annotation_rows}
    by_chapter: dict[int, list[str]] = defaultdict(list)
    for section in CATALOGUE:
        by_chapter[section.chapter].append(section.id)
    omitted = {
        chapter
        for chapter, ids in by_chapter.items()
        if all(states.get(id, SectionState(id)).status == "n/a" for id in ids)
    }
    chapter_numbers = {
        chapter: index
        for index, chapter in enumerate(
            (number for number in sorted(by_chapter) if number not in omitted), 1
        )
    }
    numbers: dict[str, str] = {}
    siblings: dict[str | None, int] = defaultdict(int)
    nodes: list[OutlineNode] = []
    for section in CATALOGUE:
        state = states.get(section.id, SectionState(section.id))
        if section.parent is None:
            number = str(chapter_numbers.get(section.chapter, section.chapter))
        else:
            if state.status != "n/a":
                siblings[section.parent] += 1
            number = f"{numbers[section.parent]}.{siblings[section.parent]}"
        numbers[section.id] = number
        missing: list[str] = []
        for ref in section.facts:
            matches = fact_fields(ref, fields)
            missing.extend(field.label for field in matches if field.presence != "found")
        note_row = notes.get(f"note:{section.id}")
        nodes.append(
            OutlineNode(
                id=section.id,
                parent=section.parent,
                chapter=section.chapter,
                number=number,
                title=section.title,
                kind=section.kind,
                status=state.status.value,
                computed_status=_computed(section, state, materials, fields).value,
                stale=state.stale,
                reason=state.reason,
                changed_input=state.changed_input,
                applicability_reason=state.applicability_reason,
                awaits=[item.value for item in section.awaits],
                missing_facts=missing,
                revision=state.revision,
                note=Annotation(text=str(note_row["value"]), revision=int(note_row["revision"]))
                if note_row
                else None,
                answered=state.status in {"done", "n/a"},
            )
        )
    deadline = notes.get("deadline")
    applicable = [number for number in chapter_numbers]
    written = sum(
        all(
            states.get(id, SectionState(id)).status in {"drafted", "done", "n/a"}
            for id in by_chapter[number]
        )
        for number in applicable
    )
    visit = fields.get("visit.date")
    return AuditOutline(
        nodes=nodes,
        deadline=Deadline(
            value=str(deadline["value"]) if deadline else None,
            revision=int(deadline["revision"]) if deadline else 0,
        ),
        visit_date=str(visit.value) if visit and visit.value is not None else None,
        answered=sum(node.answered for node in nodes),
        total=len(nodes),
        written=written,
        chapters=len(chapter_numbers),
    )
