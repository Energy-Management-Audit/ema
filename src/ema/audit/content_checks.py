"""Content gaps that block a final audit deliverable."""

from __future__ import annotations

import sqlite3

from ema.audit.ai_wording import ai_wording
from ema.audit.visit import slug
from ema.core.review.models import Field, Issue
from ema.core.review.section_transition import SectionState, Status


def content_issues(db: sqlite3.Connection, job: str) -> list[Issue]:
    fields = {
        str(row["key"]): Field.model_validate_json(row["data"])
        for row in db.execute("SELECT key,data FROM fields WHERE job_id=?", (job,))
    }
    not_applicable = {
        str(row["section_id"])
        for row in db.execute("SELECT section_id,data FROM section_states WHERE job_id=?", (job,))
        if SectionState.parse(row["data"]).status == Status.NA
    }
    count_field = fields.get("audit_measure.count")
    measure_count = (
        int(count_field.value) if count_field and count_field.value is not None else None
    )
    issues: list[Issue] = []
    active_slots = [
        (str(row["name"]), str(row["file_sha"]))
        for row in db.execute(
            "SELECT s.name, v.file_sha FROM slots s JOIN slot_versions v ON v.job_id=s.job_id "
            "AND v.slot=s.name AND v.version=s.active_version "
            "WHERE s.job_id=? AND (s.name LIKE 'visit/meter/%' OR s.name LIKE 'visit/thermal/%')",
            (job,),
        )
    ]
    active_photos = {sha[:8] for _, sha in active_slots}
    active_panels = {
        slug(parts[2])
        for name, _ in active_slots
        if (parts := name.split("/"))[:2] == ["visit", "meter"] and len(parts) == 4
    }
    for key, field in sorted(fields.items()):
        parts = key.split(".")
        photo_id = (
            parts[2]
            if len(parts) >= 4 and parts[0] == "meter"
            else parts[1]
            if len(parts) >= 3 and parts[0] == "thermal"
            else None
        )
        device_panel = (
            parts[1] if len(parts) == 3 and parts[0] == "meter" and parts[2] == "device" else None
        )
        if field.needs_confirmation and (
            photo_id in active_photos or device_panel in active_panels
        ):
            issues.append(
                Issue(
                    code="reading_unconfirmed",
                    field_id=field.id,
                    message=f"Confirmaţi valoarea de pe fotografie: {field.label}",
                )
            )
        if not key.startswith("narrative.") or key.removeprefix("narrative.") in not_applicable:
            continue
        if key.startswith("narrative.ch6.measure.") and measure_count is not None:
            suffix = key.removeprefix("narrative.ch6.measure.")
            if suffix.isdecimal() and int(suffix) > measure_count:
                continue
        if (
            isinstance(field.value, str)
            and field.review != "rejected"
            and (wording := ai_wording(field.value))
        ):
            issues.append(
                Issue(
                    code="ai_wording",
                    field_id=field.id,
                    message=f"Textul menţionează AI („{wording}”): {field.label}",
                )
            )
        if field.value is None or field.review == "rejected":
            issues.append(
                Issue(
                    code="narrative_missing",
                    field_id=field.id,
                    message=f"Textul lipseşte: {field.label}",
                )
            )
    return issues
