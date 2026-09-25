"""Persisted reporting runs over uploaded annex workbooks."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from ema.clients.registry import get_client
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, create_job, run_stage
from ema.core.workspace import Workspace
from ema.reporting import generate
from ema.reporting.writer import write_report


def start_run(ws: Workspace, years: list[int], client_ids: list[str]) -> dict[str, Any]:
    if not years or any(year < 1 for year in years) or years != sorted(set(years)):
        raise EmaError("invalid_year", "Anii raportării sunt invalizi.", "")
    if not client_ids or len(client_ids) != len(set(client_ids)):
        raise EmaError("invalid_id", "Lista clienților este invalidă.", "")
    sources: list[tuple[str, str, Path]] = []
    absent: list[dict[str, Any]] = []
    for client_id in client_ids:
        get_client(ws, client_id)
        with ws.connect() as db:
            rows = db.execute(
                "SELECT sha FROM client_uploads WHERE client_id=? AND kind IN ('xls','xlsx') "
                "ORDER BY created_at,sha",
                (client_id,),
            ).fetchall()
        if not rows:
            absent.append(
                {"client_id": client_id, "code": "annex_missing", "detail": "Anexa lipsește."}
            )
        for row in rows:
            sha = str(row["sha"])
            sources.append((client_id, sha, ws.file_path(client_id, sha)))
    job = create_job(ws, "reporting", "reporting", max(years))
    run_id = uuid.uuid4().hex
    with ws.connect() as db:
        db.execute(
            "INSERT INTO reporting_runs"
            "(id,job_id,years_json,client_ids_json,state,exceptions_json) "
            "VALUES (?,?,?,?,?,?)",
            (
                run_id,
                job,
                json.dumps(years),
                json.dumps(client_ids),
                "running",
                json.dumps(absent),
            ),
        )

    def stage(ctx: StageContext) -> StageOutcome:
        for client_id, sha, _ in sources:
            ctx.inputs[f"file:{client_id}:{sha}"] = sha
            with ws.connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO run_inputs(run_id,client_slug,file_sha) VALUES (?,?,?)",
                    (ctx.run_id, client_id, sha),
                )
        result = generate([path for _, _, path in sources], tuple(years))
        exceptions = list(absent)
        source_clients = {path: client_id for client_id, _, path in sources}
        for item in result.exceptions:
            exceptions.append(
                {
                    "client_id": source_clients.get(item.source, ""),
                    "code": item.severity,
                    "detail": item.situation,
                }
            )
        output = ctx.artifact_dir() / "Raportare.xlsx"
        write_report(result, output)
        ctx.save_output(output, "Raportare.xlsx", kind="final")
        with ws.connect() as db:
            db.execute(
                "UPDATE reporting_runs SET exceptions_json=? WHERE id=?",
                (json.dumps(exceptions, ensure_ascii=False), run_id),
            )
        ctx.progress(len(sources), len(sources), "Raportare finalizată")
        return StageOutcome()

    def finish(db: sqlite3.Connection, state: str) -> None:
        output = db.execute(
            "SELECT id FROM outputs WHERE job_id=? AND kind='final' ORDER BY seq DESC LIMIT 1",
            (job,),
        ).fetchone()
        db.execute(
            "UPDATE reporting_runs SET state=?,output_id=? WHERE id=?",
            (state, output["id"] if output else None, run_id),
        )

    run_stage(ws, job, "reporting", stage, on_finish=finish)
    return get_run(ws, run_id)


def get_run(ws: Workspace, run_id: str) -> dict[str, Any]:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM reporting_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise EmaError("run_missing", "Raportarea nu există.", "")
        if row["state"] == "running":
            job = db.execute("SELECT state FROM jobs WHERE id=?", (row["job_id"],)).fetchone()
            if job is not None and job["state"] in {"failed", "cancelled"}:
                db.execute(
                    "UPDATE reporting_runs SET state=? WHERE id=?",
                    (job["state"], run_id),
                )
                row = db.execute("SELECT * FROM reporting_runs WHERE id=?", (run_id,)).fetchone()
                assert row is not None
    return {
        "id": str(row["id"]),
        "years": json.loads(str(row["years_json"])),
        "client_ids": json.loads(str(row["client_ids_json"])),
        "state": str(row["state"]),
        "exceptions": json.loads(str(row["exceptions_json"])),
        "output_id": row["output_id"],
    }
