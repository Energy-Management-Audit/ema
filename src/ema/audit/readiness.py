"""Final audit readiness, using reviewed section and field labels."""

# pyright: reportPrivateUsage=false

import sqlite3

from ema.audit import sections
from ema.audit.applicability import applies, fact_fields
from ema.audit.catalogue import CATALOGUE
from ema.audit.catalogue_labels import CEDILLA
from ema.audit.chapter_readiness import empty_chapters
from ema.core.review.models import Issue, Readiness
from ema.core.review.section_transition import Status
from ema.core.workspace import Workspace


def audit_readiness(ws: Workspace, job: str, db: sqlite3.Connection | None = None) -> Readiness:
    if db is None:
        with ws.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return audit_readiness(ws, job, connection)
    sections.refresh_staleness(ws, job, db)
    states = sections.statuses(ws, job, db)
    materials, facts = sections._inputs(ws, job, db)
    issues: list[Issue] = []
    for section, state in zip(CATALOGUE, states, strict=True):
        if state.stale:
            issues.append(
                Issue(
                    code="stale", message=f"Refaceţi secţiunea: {section.title.translate(CEDILLA)}"
                )
            )
        if (
            state.status == Status.NA
            and state.na_applicable is not True
            and applies(section.applies_when, materials, facts) is True
        ):
            issues.append(
                Issue(
                    code="na_recheck",
                    message=f"Reverificaţi n/a: {section.title.translate(CEDILLA)}",
                )
            )
        if state.status not in (Status.DONE, Status.NA):
            applicable = applies(section.applies_when, materials, facts)
            next_step = (
                "aşteaptă preluarea dosarului"
                if applicable is None
                else (
                    "Confirmaţi că nu se aplică"
                    if applicable is False
                    else "Completaţi şi confirmaţi secţiunea"
                )
            )
            issues.append(
                Issue(
                    code="section_open", message=f"{section.title.translate(CEDILLA)}: {next_step}"
                )
            )
        for ref in section.facts:
            for field in fact_fields(ref, facts):
                if field.confidence == "conflict":
                    issues.append(
                        Issue(
                            code="conflict",
                            field_id=field.id,
                            message=(
                                f"Rezolvaţi conflictul: "
                                f"{section.title.translate(CEDILLA)} / {field.label}"
                            ),
                        )
                    )
    issues.extend(empty_chapters(states))
    return Readiness(
        draft_ok=True,
        final_ok=not issues,
        blocking=issues,
        next=[issue.message for issue in issues],
    )
