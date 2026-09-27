"""The report outline numbers only applicable siblings and keeps human annotations."""

import json
from datetime import date
from pathlib import Path

from ema.audit.annotations import put_deadline, put_note
from ema.audit.catalogue import CATALOGUE
from ema.audit.outline import outline
from ema.core.jobs import create_job
from ema.core.review.models import Field
from ema.core.review.section_transition import SectionState, Status
from ema.core.workspace import Workspace


def _state(ws: Workspace, job: str, section: str, status: Status) -> None:
    state = SectionState(section, status)
    with ws.connect() as db:
        db.execute(
            "INSERT INTO section_states (job_id,section_id,revision,data) VALUES (?,?,?,?)",
            (job, section, state.revision, json.dumps(state.payload())),
        )


def test_numbering_skips_na_chapter_and_child(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    for section in CATALOGUE:
        if section.chapter == 5 or section.id == "ch3.process":
            _state(ws, job, section.id, Status.NA)
    view = outline(ws, job)
    nodes = {node.id: node for node in view.nodes}
    assert nodes["ch6"].number == "5"
    assert nodes["ch3.process"].status == "n/a"
    following = next(
        section for section in CATALOGUE if section.parent == "ch3" and section.id != "ch3.process"
    )
    assert nodes[following.id].number.startswith("3.")
    assert view.chapters == len({section.chapter for section in CATALOGUE}) - 1
    assert view.answered >= sum(section.chapter == 5 for section in CATALOGUE)
    assert nodes["ch6.measure"].status == "missing"


def test_missing_field_labels_and_annotations(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "ws")
    job = create_job(ws, "audit", "synthetic", 2026)
    field = Field(
        id="field-1",
        job_id=job,
        chapter="ch2",
        key="audit.company_name",
        label="Numele societăţii",
        value_type="text",
        state="extracted",
        presence="not_found",
    )
    with ws.connect() as db:
        db.execute(
            "INSERT INTO fields (id,job_id,key,revision,data) VALUES (?,?,?,?,?)",
            (field.id, job, field.key, field.revision, field.model_dump_json()),
        )
    put_note(ws, job, "ch2.date_generale", "Verifică anexa", 0)
    put_deadline(ws, job, date(2026, 12, 1), 0)
    view = outline(ws, job)
    general = next(node for node in view.nodes if node.id == "ch2.date_generale")
    assert "Numele societăţii" in general.missing_facts
    assert general.note is not None and general.note.text == "Verifică anexa"
    assert view.deadline.value == "2026-12-01"
