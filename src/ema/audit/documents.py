"""Read the audit's active documents and their last intake outcomes."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel

from ema.audit.visit import VisitView, visit_view_from_slots
from ema.core.errors import EmaError
from ema.core.jobs.reads import run_current
from ema.core.workspace import SlotVersion, Workspace


class DocFile(BaseModel):
    slot: str
    name: str
    kind: str
    size_bytes: int
    version: int
    slot_revision: int
    sha: str
    status: Literal[
        "read", "reading", "needs_conversion", "scanned", "protected", "failed", "unread"
    ]
    item: int | None = None
    item_text: str | None = None
    error_code: str | None = None
    reason: str | None = None


class ChecklistRow(BaseModel):
    number: int
    text: str
    received: bool


class StageView(BaseModel):
    state: str
    current: bool


class AuditDocuments(BaseModel):
    files: list[DocFile]
    anexa: DocFile | None
    measures: DocFile | None
    checklist: list[ChecklistRow] | None
    missing: list[int]
    unclassified: list[str]
    visit: VisitView | None
    runs: dict[str, StageView | None]


_REASONS = {
    "needs_conversion": "Word nu l-a putut converti.",
    "file_type": "Tipul fişierului nu este acceptat.",
    "conversion_timeout": "Conversia a durat prea mult.",
}
_STAGES = ("intake", "read", "visit", "measures")


def documents(ws: Workspace, job: str) -> AuditDocuments:  # noqa: C901
    with ws.connect() as db:
        db.execute("BEGIN")
        job_row = db.execute(
            "SELECT type,client_slug,relative_path FROM jobs WHERE id=? AND deleted=0", (job,)
        ).fetchone()
        if job_row is None:
            raise EmaError("job_missing", "Lucrarea nu există.", job)
        if job_row["type"] != "audit":
            raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
        slots = db.execute(
            "SELECT v.*,s.revision AS slot_revision,u.original_name,u.kind,"
            "COALESCE(u.size_bytes,f.size) AS size_bytes FROM slots s "
            "JOIN slot_versions v ON v.job_id=s.job_id AND v.slot=s.name "
            "AND v.version=s.active_version "
            "LEFT JOIN files f ON f.sha=v.file_sha AND f.client_slug=? "
            "LEFT JOIN client_uploads u ON u.client_id=? "
            "AND u.sha=COALESCE(v.converted_from,v.file_sha) "
            "WHERE s.job_id=? ORDER BY s.name",
            (job_row["client_slug"], job_row["client_slug"], job),
        ).fetchall()
        run_rows = db.execute(
            "SELECT id,stage,state FROM runs WHERE job_id=? AND stage IN "
            "('intake','read','visit','measures') ORDER BY started_at DESC",
            (job,),
        ).fetchall()
        latest = {str(row["stage"]): row for row in reversed(run_rows)}
        runs: dict[str, StageView | None] = {
            stage: StageView(
                state=str(latest[stage]["state"]), current=run_current(db, str(latest[stage]["id"]))
            )
            if stage in latest
            else None
            for stage in _STAGES
        }
        form_reads = {
            slot: bool(
                (stage_run := latest.get(stage)) is not None
                and (view := runs[stage]) is not None
                and view.current
                and db.execute(
                    "SELECT 1 FROM run_reads WHERE run_id=? AND table_name='slots' "
                    "AND row_id=? AND revision="
                    "(SELECT revision FROM slots WHERE job_id=? AND name=?)",
                    (stage_run["id"], f"{job}:{slot}", job, slot),
                ).fetchone()
            )
            for slot, stage in (("anexa", "read"), ("measures", "measures"))
        }
    intake = latest.get("intake")
    report: dict[str, Any] = {}
    if intake is not None:
        path = ws.path(
            str(
                Path(str(job_row["relative_path"]))
                / "work"
                / "intake"
                / str(intake["id"])
                / "completeness.json"
            )
        )
        if path.exists():
            report = json.loads(path.read_text(encoding="utf-8"))
    records: dict[str, dict[str, Any]] = {
        str(item["slot"]): item
        for item in cast("list[dict[str, Any]]", report.get("files", []))
        if "slot" in item
    }
    checklist = (
        [
            ChecklistRow(
                number=int(item["number"]),
                text=str(item["text"]),
                received=bool(report.get("received", {}).get(str(item["number"]))),
            )
            for item in report.get("checklist", [])
        ]
        if "checklist" in report
        else None
    )
    checklist_text = {row.number: row.text for row in checklist or []}
    running = any(
        (view := runs[stage]) is not None and view.state == "running"
        for stage in ("intake", "read")
    )
    measures_running = runs["measures"] is not None and runs["measures"].state == "running"
    read_current = runs["read"] is not None and runs["read"].current

    def make_file(row: sqlite3.Row) -> DocFile:
        slot = str(row["slot"])
        sha = str(row["file_sha"])
        photo = slot == "cover/photo"
        record = records.get(slot)
        if record is not None and record.get("file_sha") != sha:
            record = None
        status: Literal[
            "read", "reading", "needs_conversion", "scanned", "protected", "failed", "unread"
        ] = "unread"
        if not photo and (
            (slot == "measures" and measures_running) or (slot != "measures" and running)
        ):
            status = "reading"
        elif form_reads.get(slot):
            status = "read"
        elif record is not None:
            intake_status = str(record.get("status", ""))
            if intake_status in {"failed", "needs_conversion", "scanned", "protected"}:
                status = cast(
                    "Literal['failed', 'needs_conversion', 'scanned', 'protected']", intake_status
                )
            elif read_current:
                status = "read"
        item = int(record["item"]) if record and record.get("item") is not None else None
        code = str(record["error_code"]) if record and record.get("error_code") else None
        return DocFile(
            slot=slot,
            name=str(row["original_name"] or (row["origin"] if photo else Path(slot).name)),
            kind=str(
                row["kind"]
                or (record.get("kind") if record else None)
                or (Path(str(row["origin"])).suffix.lstrip(".") if photo else "unknown")
            ),
            size_bytes=int(row["size_bytes"] or 0),
            version=int(row["version"]),
            slot_revision=int(row["slot_revision"]),
            sha=sha,
            status=status,
            item=item,
            item_text=checklist_text.get(item) if item is not None else None,
            error_code=code,
            reason=_REASONS.get(code, "Fişierul nu a putut fi citit.") if code else None,
        )

    result = [
        make_file(row)
        for row in slots
        if str(row["slot"]).startswith("dossier/") or row["slot"] == "cover/photo"
    ]
    result.sort(key=lambda file: (file.item is None, file.item or 0, file.name.casefold()))
    anexa = next((make_file(row) for row in slots if row["slot"] == "anexa"), None)
    measures = next((make_file(row) for row in slots if row["slot"] == "measures"), None)
    visit_slots = [
        SlotVersion(
            job,
            str(row["slot"]),
            int(row["version"]),
            str(row["file_sha"]),
            str(row["origin"]),
            row["converted_from"],
        )
        for row in slots
        if str(row["slot"]).startswith("visit/")
    ]
    return AuditDocuments(
        files=result,
        anexa=anexa,
        measures=measures,
        checklist=checklist,
        missing=[int(number) for number in report.get("missing", [])],
        unclassified=[str(slot) for slot in report.get("unclassified", [])],
        visit=visit_view_from_slots(visit_slots) if visit_slots else None,
        runs=runs,
    )
