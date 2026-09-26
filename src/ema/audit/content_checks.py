"""Content gaps that block a final audit deliverable."""

from __future__ import annotations

import sqlite3

from ema.core.review.models import Field, Issue


def content_issues(db: sqlite3.Connection, job: str) -> list[Issue]:
    fields = {
        str(row["key"]): Field.model_validate_json(row["data"])
        for row in db.execute("SELECT key,data FROM fields WHERE job_id=?", (job,))
    }
    count_field = fields.get("audit_measure.count")
    measure_count = (
        int(count_field.value) if count_field and count_field.value is not None else None
    )
    issues: list[Issue] = []
    for key, field in sorted(fields.items()):
        if not key.startswith("narrative."):
            continue
        if key.startswith("narrative.ch6.measure.") and measure_count is not None:
            suffix = key.removeprefix("narrative.ch6.measure.")
            if suffix.isdecimal() and int(suffix) > measure_count:
                continue
        if field.value is None or field.review == "rejected":
            issues.append(
                Issue(
                    code="narrative_missing",
                    field_id=field.id,
                    message=f"Textul lipseşte: {field.label}",
                )
            )
    return issues
