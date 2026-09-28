"""Shared W3 readiness and the audit render use cases."""

from __future__ import annotations

import sqlite3

from ema.audit.content_checks import content_issues
from ema.audit.render import start_audit_render
from ema.audit.render_bindings import COVER_SLOT
from ema.audit.render_report import newest_final
from ema.audit.sections import audit_readiness
from ema.core.errors import EmaError
from ema.core.jobs import status, subscribe
from ema.core.jobs.reads import revision
from ema.core.review.models import Issue, Readiness
from ema.core.workspace import Workspace


def _newest_docx_in(db: sqlite3.Connection, job: str, stage: str) -> tuple[str, str, str] | None:
    """(run, output id, sha) of the newest ready run's docx output of the stage."""
    row = db.execute(
        "SELECT o.run_id,o.id,o.sha FROM outputs o JOIN runs r ON r.id=o.run_id "
        "WHERE o.job_id=? AND r.stage=? AND r.state='ready' AND o.relative_path LIKE '%.docx' "
        "ORDER BY o.seq DESC LIMIT 1",
        (job, stage),
    ).fetchone()
    return (str(row["run_id"]), str(row["id"]), str(row["sha"])) if row else None


def _cover_changed(db: sqlite3.Connection, job: str) -> bool:
    """The newest draft showed another cover photo (or none) than the one uploaded now: a final
    would print a photo nobody saw in a draft."""
    draft = _newest_docx_in(db, job, "audit_render")
    if draft is None:
        return False
    reads = {
        (str(row["table_name"]), str(row["row_id"])): int(row["revision"])
        for row in db.execute(
            "SELECT table_name,row_id,revision FROM run_reads WHERE run_id=? "
            "AND ((table_name='slots.collection' AND row_id=?) "
            "OR (table_name='slots' AND row_id=?))",
            (draft[0], f"{job}:cover", f"{job}:{COVER_SLOT}"),
        )
    }
    photo = ("slots", f"{job}:{COVER_SLOT}")
    wanted = [("slots.collection", f"{job}:cover"), *([photo] if photo in reads else [])]
    return any(reads.get(key) != revision(db, *key) for key in wanted)


class AuditWorkflow:
    def readiness(self, ws: Workspace, job: str) -> Readiness:
        with ws.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self.readiness_in_tx(ws, job, db)

    def readiness_in_tx(self, ws: Workspace, job: str, db: sqlite3.Connection) -> Readiness:
        result = audit_readiness(ws, job, db)
        issues = content_issues(db, job)
        final = newest_final(ws, db, job)
        if final is not None and not final[2]:
            # The data or the base changed after the final: it is not what would be delivered.
            issues.append(
                Issue(
                    code="final_stale",
                    message="Versiunea finală nu mai corespunde datelor. Generează-o din nou.",
                )
            )
        if _cover_changed(db, job):
            issues.append(
                Issue(
                    code="cover_photo_changed",
                    message="Fotografia sediului s-a schimbat după ciornă. Refaceţi ciorna.",
                )
            )
        result.blocking.extend(issues)
        result.next.extend(issue.message for issue in issues)
        result.final_ok = not result.blocking
        return result

    def readiness_snapshot(self, ws: Workspace, job: str) -> dict[str, object]:
        with ws.connect() as db:
            return self.readiness_snapshot_in_tx(db, job)

    def readiness_snapshot_in_tx(self, db: sqlite3.Connection, job: str) -> dict[str, object]:
        sections = [
            tuple(row)
            for row in db.execute(
                "SELECT section_id,revision FROM section_states WHERE job_id=? ORDER BY section_id",
                (job,),
            )
        ]
        materials = [
            tuple(row)
            for row in db.execute(
                "SELECT kind,present,source FROM audit_materials WHERE job_id=? ORDER BY kind",
                (job,),
            )
        ]
        # A new draft changes what the auditor approves, so it changes the readiness hash.
        draft = _newest_docx_in(db, job, "audit_render")
        return {
            "sections": sections,
            "materials": materials,
            "render": [draft[0], draft[2]] if draft else None,
            "final": list(final) if (final := _newest_docx_in(db, job, "audit_final")) else None,
        }

    def start_final(self, ws: Workspace, job: str, *, on_revision: int | None = None) -> str:
        # A stale final is what a new final replaces, so it never blocks making one.
        blocking = [
            issue for issue in self.readiness(ws, job).blocking if issue.code != "final_stale"
        ]
        if blocking:
            raise EmaError("not_ready", "Lucrarea nu este pregătită pentru export.", job)
        return start_audit_render(ws, job, "final", on_revision=on_revision)

    def render(self, ws: Workspace, job: str, kind: str) -> str:
        if kind == "draft":
            run = start_audit_render(ws, job, "draft")
            for _ in subscribe(ws, job):
                pass
            record = next(item for item in status(ws, job).runs if item["id"] == run)
            if record["state"] != "ready":
                raise EmaError(
                    "audit_render_failed", "Generarea raportului a eşuat.", str(record["error"])
                )
        elif kind != "final":
            raise EmaError("output_kind", "Tipul documentului este invalid.", kind)
        with ws.connect() as db:
            found = _newest_docx_in(db, job, "audit_render" if kind == "draft" else "audit_final")
        if found is None:
            raise EmaError("output_missing", "Documentul lipseşte.", job)
        return found[1]
