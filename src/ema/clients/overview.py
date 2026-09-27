"""Client list projection from registry, indexed annexes, and confirmed memory."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from ema.core.workspace import Workspace


def _newest_annexes(db: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    rows = db.execute(
        "SELECT client_id,year,data FROM client_annexes ORDER BY year DESC,read_at DESC,sha DESC"
    ).fetchall()
    result: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        result.setdefault(str(row["client_id"]), []).append(row)
    return result


def overview(ws: Workspace) -> list[dict[str, Any]]:
    with ws.connect() as db:
        db.execute("BEGIN")
        clients = db.execute("SELECT * FROM clients ORDER BY name COLLATE NOCASE,id").fetchall()
        annexes = _newest_annexes(db)
        snapshots = {
            str(row["client_id"]): cast(dict[str, Any], json.loads(str(row["payload_json"])))
            for row in db.execute(
                "SELECT client_id,payload_json FROM anaf_snapshots WHERE payload_json IS NOT NULL"
            )
        }
        pods: dict[str, list[str]] = {}
        for row in db.execute(
            "SELECT j.client_slug,m.identifier FROM client_memory m "
            "JOIN decisions d ON d.id=m.decision_id "
            "JOIN jobs j ON j.id=m.job_id "
            "WHERE m.kind='pod' AND j.deleted=0 "
            "AND json_extract(d.data,'$.undone_by') IS NULL"
        ):
            pods.setdefault(str(row["client_slug"]), []).append(str(row["identifier"]))
    result: list[dict[str, Any]] = []
    for client in clients:
        client_id = str(client["id"])
        records = annexes.get(client_id, [])
        newest: dict[str, Any] = (
            cast(dict[str, Any], json.loads(str(records[0]["data"]))) if records else {}
        )
        consumption = next(
            (
                {"year": int(row["year"]), "total_tep": json.loads(str(row["data"]))["total_tep"]}
                for row in records
                if json.loads(str(row["data"])).get("total_tep") is not None
            ),
            None,
        )
        found = cast(list[dict[str, Any]], snapshots.get(client_id, {}).get("found") or [])
        company: dict[str, Any] = found[0] if found else {}
        social = cast(dict[str, Any], company.get("adresa_sediu_social") or {})
        result.append(
            {
                "id": client_id,
                "name": client["name"],
                "cui": client["cui"],
                "county": social.get("sdenumire_Judet"),
                "caen": client["caen"] or newest.get("caen_code"),
                "caen_description": newest.get("caen_description"),
                "anaf_refreshed_at": client["anaf_refreshed_at"],
                "annex_years": sorted({int(row["year"]) for row in records}, reverse=True),
                "consumption": consumption,
                "pods": sorted(set(pods.get(client_id, []))),
            }
        )
    return result
