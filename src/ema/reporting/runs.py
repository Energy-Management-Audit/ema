"""Persisted reporting runs over uploaded annex workbooks."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path
from typing import Any

from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, create_job, run_stage, subscribe
from ema.core.workspace import Workspace
from ema.energy_data.annex_index import import_annexes
from ema.reporting import ReportException, generate
from ema.reporting.sources import select_sources
from ema.reporting.writer import write_report


def start_run(
    ws: Workspace,
    years: list[int],
    client_ids: list[str],
    *,
    source_exceptions: tuple[ReportException, ...] = (),
) -> dict[str, Any]:
    if not years or any(year < 1 for year in years) or years != sorted(set(years)):
        raise EmaError("invalid_year", "Anii raportării sunt invalizi.", "")
    if not client_ids or len(client_ids) != len(set(client_ids)):
        raise EmaError("invalid_id", "Lista clienţilor este invalidă.", "")
    sources, absent = select_sources(ws, client_ids)
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
        result = replace(result, exceptions=(*source_exceptions, *result.exceptions))
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
        write_report(result, output, firm_name=load_settings(ws).firm_name)
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


def _get_run(db: sqlite3.Connection, run_id: str) -> dict[str, Any]:
    row = db.execute(
        "SELECT r.*,j.created_at,j.state AS job_state FROM reporting_runs r "
        "JOIN jobs j ON j.id=r.job_id WHERE r.id=?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise EmaError("run_missing", "Raportarea nu există.", run_id)
    state = str(row["state"])
    if state == "running" and row["job_state"] in {"failed", "cancelled"}:
        state = str(row["job_state"])
        db.execute("UPDATE reporting_runs SET state=? WHERE id=?", (state, run_id))
    return {
        "id": str(row["id"]),
        "job_id": str(row["job_id"]),
        "created_at": str(row["created_at"]),
        "years": json.loads(str(row["years_json"])),
        "client_ids": json.loads(str(row["client_ids_json"])),
        "state": state,
        "exceptions": json.loads(str(row["exceptions_json"])),
        "output_id": row["output_id"],
    }


def get_run(ws: Workspace, run_id: str) -> dict[str, Any]:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        return _get_run(db, run_id)


def list_runs(ws: Workspace) -> list[dict[str, Any]]:
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        rows = db.execute(
            "SELECT r.id FROM reporting_runs r JOIN jobs j ON j.id=r.job_id ORDER BY r.rowid DESC"
        ).fetchall()
        return [_get_run(db, str(row["id"])) for row in rows]


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


def generate_from_sources(ws: Workspace, paths: list[Path], years: list[int], output: Path) -> Path:
    """Import folder sources and wait for the same indexed reporting run as the UI."""
    with ExitStack() as stack:
        imported = import_annexes(
            ws, [(path.name, stack.enter_context(path.open("rb"))) for path in paths]
        )
    if not imported.imported:
        details = "; ".join(f"{item.file_name}: {item.reason}" for item in imported.ignored)
        raise EmaError("not_ready", "Unele anexe nu pot fi citite.", details)
    client_ids = list(dict.fromkeys(item.client_id for item in imported.imported))
    rejected = tuple(
        ReportException("EROARE", Path(item.file_name), None, item.reason, "Sursa a fost exclusă.")
        for item in imported.ignored
    )
    started = start_run(ws, years, client_ids, source_exceptions=rejected)
    for _ in subscribe(ws, str(started["job_id"])):
        pass
    run = get_run(ws, str(started["id"]))
    if run["state"] != "ready":
        raise EmaError("run_not_ready", "Raportul nu este gata.", str(run["state"]))
    with ws.connect() as db:
        row = db.execute(
            "SELECT relative_path FROM outputs WHERE id=?", (run["output_id"],)
        ).fetchone()
        assert row is not None
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ws.path(str(row["relative_path"])), output)
    return output
