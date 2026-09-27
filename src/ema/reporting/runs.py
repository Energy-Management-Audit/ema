"""Persisted reporting runs over uploaded annex workbooks."""

from __future__ import annotations

import json
import sqlite3
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from ema.clients.registry import get_client
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, create_job, run_stage
from ema.core.workspace import Workspace
from ema.energy_data.annex_index import indexed
from ema.reporting import generate
from ema.reporting.writer import write_report


def start_run(ws: Workspace, years: list[int], client_ids: list[str]) -> dict[str, Any]:  # noqa: C901, PLR0915
    if not years or any(year < 1 for year in years) or years != sorted(set(years)):
        raise EmaError("invalid_year", "Anii raportării sunt invalizi.", "")
    if not client_ids or len(client_ids) != len(set(client_ids)):
        raise EmaError("invalid_id", "Lista clienţilor este invalidă.", "")
    sources: list[tuple[str, str, Path, Path]] = []
    absent: list[dict[str, Any]] = []
    annexes = indexed(ws)
    for client_id in client_ids:
        get_client(ws, client_id)
        records = annexes.get(client_id, [])
        if not records:
            absent.append(
                {"client_id": client_id, "code": "annex_missing", "detail": "Anexa lipseşte."}
            )
            continue
        seen: set[tuple[int, str]] = set()
        for record in records:
            beneficiary = " ".join(str(record.data.get("name") or "").casefold().split())
            key = (record.year, beneficiary)
            if key in seen:
                continue
            seen.add(key)
            raw_name = str(record.data.get("file_name") or f"{record.sha}.xlsx")
            display_name = unicodedata.normalize("NFC", raw_name)
            sources.append(
                (
                    client_id,
                    record.sha,
                    ws.file_path(client_id, record.sha),
                    Path(client_id, display_name),
                )
            )
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
        for client_id, sha, _, _ in sources:
            ctx.inputs[f"file:{client_id}:{sha}"] = sha
            with ws.connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO run_inputs(run_id,client_slug,file_sha) VALUES (?,?,?)",
                    (ctx.run_id, client_id, sha),
                )
        result = generate(
            [path for _, _, path, _ in sources],
            tuple(years),
            {path: logical for _, _, path, logical in sources},
        )
        exceptions = list(absent)
        source_clients = {
            logical: (client_id, logical.name) for client_id, _, _, logical in sources
        }
        for item in result.exceptions:
            client_id, source_name = source_clients.get(item.source, ("", None))
            exceptions.append(
                {
                    "client_id": client_id,
                    "code": item.severity,
                    "detail": item.situation,
                    "source_name": source_name,
                    "beneficiary": item.beneficiary,
                    "decision": item.decision,
                    "ref": item.ref,
                }
            )
        rows: dict[str, list[dict[str, Any]]] = {}
        counts: dict[str, int] = {}
        for year in years:
            year_rows: list[dict[str, Any]] = []
            for company in result.companies:
                measures = company.measures.get(year, ())
                if not measures:
                    continue
                client_id, _ = source_clients.get(company.source, ("", None))
                year_rows.append(
                    {
                        "nr": len(year_rows) + 1,
                        "beneficiary": company.name,
                        "client_id": client_id,
                        "measures": [
                            {
                                "description": measure.description,
                                "saving_tep": measure.saving_tep,
                                "cost_thousand_lei": measure.cost_thousand_lei,
                            }
                            for measure in measures
                        ],
                    }
                )
            rows[str(year)] = year_rows
            counts[str(year)] = len(year_rows)
        preview = {
            "years": years,
            "consumption_year": result.consumption_year,
            "read": len(sources),
            "companies_per_year": counts,
            "rows": rows,
        }
        (ctx.artifact_dir() / "report.json").write_text(
            json.dumps(preview, ensure_ascii=False), encoding="utf-8"
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
        "job_id": str(row["job_id"]),
        "created_at": _created_at(ws, str(row["job_id"])),
        "years": json.loads(str(row["years_json"])),
        "client_ids": json.loads(str(row["client_ids_json"])),
        "state": str(row["state"]),
        "exceptions": json.loads(str(row["exceptions_json"])),
        "output_id": row["output_id"],
    }


def _created_at(ws: Workspace, job_id: str) -> str:
    with ws.connect() as db:
        row = db.execute("SELECT created_at FROM jobs WHERE id=?", (job_id,)).fetchone()
    assert row is not None
    return str(row["created_at"])


def list_runs(ws: Workspace) -> list[dict[str, Any]]:
    with ws.connect() as db:
        rows = db.execute("SELECT id FROM reporting_runs ORDER BY rowid DESC").fetchall()
    return [get_run(ws, str(row["id"])) for row in rows]


def preview(ws: Workspace, run_id: str) -> dict[str, Any]:
    run = get_run(ws, run_id)
    if run["state"] != "ready":
        raise EmaError("run_not_ready", "Raportul nu este gata.", "")
    with ws.connect() as db:
        row = db.execute(
            "SELECT id FROM runs WHERE job_id=? AND stage='reporting' "
            "ORDER BY started_at DESC LIMIT 1",
            (run["job_id"],),
        ).fetchone()
        assert row is not None
        artifact = ws.artifact_dir(db, str(run["job_id"]), "reporting", str(row["id"]))
    return json.loads((artifact / "report.json").read_text(encoding="utf-8"))
