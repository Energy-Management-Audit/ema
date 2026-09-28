"""Leave one drafted chapter for the audit UI confirmation golden."""

from __future__ import annotations

import json

from ema.audit.catalogue import CATALOGUE
from ema.audit.sections import Status, refresh_staleness, set_status, statuses
from ema.audit.sections_bulk import patch_sections
from ema.audit.workflow import AuditWorkflow
from ema.core.review import fields
from ema.core.review.section_transition import SectionState
from ema.core.workspace import Workspace

CHAPTER = {section.id: section.chapter for section in CATALOGUE}


def prepare_all_but(ws: Workspace, job: str, chapter: str) -> list[SectionState]:
    """Leave one chapter's current Ema drafts for the human UI click."""
    assert all(
        field.value is not None for field in fields(ws, job) if field.key.startswith("narrative.")
    )
    refresh_staleness(ws, job)
    left = [
        state
        for state in statuses(ws, job)
        if CHAPTER[state.section_id] == CHAPTER[chapter] and state.status == Status.DRAFTED
    ]
    assert left and all(not state.stale for state in left)
    for chapter_number in sorted(set(CHAPTER.values()) - {CHAPTER[chapter]}):
        items = [
            {
                "section_id": state.section_id,
                "status": "done",
                "on_revision": state.revision,
                "confirm": True,
            }
            for state in statuses(ws, job)
            if CHAPTER[state.section_id] == chapter_number
            and state.status == Status.DRAFTED
            and not state.stale
        ]
        if items:
            patch_sections(ws, job, items)
    for state in statuses(ws, job):
        if state.section_id not in {item.section_id for item in left} and state.status not in (
            Status.DONE,
            Status.NA,
        ):
            set_status(ws, job, state.section_id, Status.NA, "user", "golden")
    with ws.connect() as db:
        for state in left:
            row = db.execute(
                "SELECT data FROM decisions WHERE job_id=? AND field_id=? "
                "ORDER BY seq DESC LIMIT 1",
                (job, state.section_id),
            ).fetchone()
            assert row and json.loads(row["data"])["actor"] == "ema"
    readiness = AuditWorkflow().readiness(ws, job)
    titles = {
        section.title for section in CATALOGUE if section.id in {item.section_id for item in left}
    }
    assert not readiness.final_ok
    assert {
        issue.message.split(":", 1)[0]
        for issue in readiness.blocking
        if issue.code == "section_open"
    } == titles
    assert len([issue for issue in readiness.blocking if issue.code == "section_open"]) == len(left)
    assert len(readiness.blocking) == len(left)
    return left
