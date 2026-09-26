"""Shared W3 readiness; rendering is introduced by S10b."""

from __future__ import annotations

import sqlite3

from ema.audit.content_checks import content_issues
from ema.audit.sections import audit_readiness
from ema.core.errors import EmaError
from ema.core.review.models import Readiness
from ema.core.workspace import Workspace


class AuditWorkflow:
    def readiness(self, ws: Workspace, job: str) -> Readiness:
        with ws.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            return self.readiness_in_tx(ws, job, db)

    def readiness_in_tx(self, ws: Workspace, job: str, db: sqlite3.Connection) -> Readiness:
        result = audit_readiness(ws, job, db)
        issues = content_issues(db, job)
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
        return {"sections": sections, "materials": materials}

    def render(self, ws: Workspace, job: str, kind: str) -> str:
        raise EmaError("not_implemented", "Generarea auditului nu este încă disponibilă.", kind)
