"""Atomic human review of multiple audit section states."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ema.audit.applicability import applies
from ema.audit.catalogue import CATALOGUE
from ema.audit.sections import (  # pyright: ignore[reportPrivateUsage]
    _computed,
    _inputs,
    _save,
    _section,
    refresh_staleness,
    statuses,
)
from ema.core.errors import EmaError
from ema.core.review.section_transition import SectionState, Status, transition
from ema.core.workspace import Workspace


def patch_sections(ws: Workspace, job: str, items: list[dict[str, Any]]) -> list[SectionState]:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT type FROM jobs WHERE id=? AND deleted=0", (job,)).fetchone()
        if row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", "")
        if row["type"] != "audit":
            raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", "")
        # A fact, material or base changed since the page was read: confirm no stale draft.
        refresh_staleness(ws, job, db)
        states = {state.section_id: state for state in statuses(ws, job, db)}
        stale = {
            str(item["section_id"])
            for item in items
            if item["status"] == Status.DONE.value
            and (state := states.get(str(item["section_id"]))) is not None
            and state.stale
        }
        if stale:
            db.commit()
            raise EmaError(
                "sections_stale",
                "Unele secţiuni au ciorna veche.",
                ",".join(section.id for section in CATALOGUE if section.id in stale),
            )
        materials, facts = _inputs(ws, job, db)
        results: list[SectionState] = []
        for item in items:
            section_id = str(item["section_id"])
            section = _section(section_id)
            state_row = db.execute(
                "SELECT data FROM section_states WHERE job_id=? AND section_id=?",
                (job, section_id),
            ).fetchone()
            before = (
                SectionState.parse(state_row["data"]) if state_row else SectionState(section_id)
            )
            if before.revision != item["on_revision"]:
                raise EmaError("stale_revision", "Secţiunea s-a modificat între timp.", "")
            to = Status(item["status"])
            if to in {Status.DONE, Status.NA} and not item.get("confirm"):
                raise EmaError("human_required", "Confirmarea umană este necesară.", "")
            after = transition(
                before,
                to,
                "user",
                item.get("reason"),
                computed=_computed(section, before, materials, facts),
            )
            if to == Status.NA:
                after = replace(
                    after, na_applicable=applies(section.applies_when, materials, facts)
                )
            results.append(_save(ws, job, before, after, "user", db=db))
        return results
