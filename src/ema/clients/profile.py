"""Client detail projection with source-labelled identity and memory."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, cast

from ema.clients.registry import validate_id
from ema.core.errors import EmaError
from ema.core.workspace import Workspace


def _identification(
    company: dict[str, Any], annex: dict[str, Any], year: int | None, retrieved: str | None
) -> dict[str, Any] | None:
    general = cast(dict[str, Any], company.get("date_generale") or {})
    if general:
        return {
            "name": general.get("denumire"),
            "cui": general.get("cui"),
            "registration": general.get("nrRegCom"),
            "address": general.get("adresa"),
            "caen": general.get("cod_CAEN"),
            "caen_description": annex.get("caen_description"),
            "source": "anaf",
            "retrieved_at": retrieved,
            "annex_year": None,
        }
    if annex:
        return {
            "name": annex.get("name"),
            "cui": annex.get("cui"),
            "registration": annex.get("registrul_comertului"),
            "address": annex.get("address"),
            "caen": annex.get("caen_code"),
            "caen_description": annex.get("caen_description"),
            "source": "annex",
            "retrieved_at": None,
            "annex_year": year,
        }
    return None


def _fiscal(company: dict[str, Any]) -> dict[str, bool | None] | None:
    if not company:
        return None
    inactive = cast(dict[str, Any], company.get("stare_inactiv") or {}).get("statusInactivi")
    vat = cast(dict[str, Any], company.get("inregistrare_scop_Tva") or {}).get("scpTVA")
    return {
        "active": None if inactive is None else not bool(inactive),
        "vat_payer": None if vat is None else bool(vat),
    }


def _memory(db: sqlite3.Connection, client_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT m.kind,m.identifier,m.job_id,d.at,d.data FROM client_memory m "
        "JOIN decisions d ON d.id=m.decision_id JOIN jobs j ON j.id=m.job_id "
        "WHERE j.client_slug=? ORDER BY d.at DESC,d.seq DESC",
        (client_id,),
    ).fetchall()
    return [
        {
            "kind": row["kind"],
            "identifier": row["identifier"],
            "job_id": row["job_id"],
            "confirmed_at": row["at"],
            "active": json.loads(str(row["data"])).get("undone_by") is None,
        }
        for row in rows
    ]


def profile(ws: Workspace, client_id: str) -> dict[str, Any]:
    validate_id(client_id)
    with ws.connect() as db:
        db.execute("BEGIN")
        row = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        if row is None:
            raise EmaError("client_missing", "Clientul nu există.", "")
        client = dict(row)
        client["sites"] = json.loads(client.pop("sites_json"))
        client["contacts"] = json.loads(client.pop("contacts_json"))
        annexes = db.execute(
            "SELECT a.sha,a.year,a.data,a.read_at,u.original_name FROM client_annexes a "
            "LEFT JOIN client_uploads u ON u.client_id=a.client_id AND u.sha=a.sha "
            "WHERE a.client_id=? ORDER BY a.year DESC,a.read_at DESC,a.sha DESC",
            (client_id,),
        ).fetchall()
        snapshot = db.execute(
            "SELECT payload_json,retrieved_at FROM anaf_snapshots WHERE client_id=?", (client_id,)
        ).fetchone()
        memory = _memory(db, client_id)
    latest: dict[str, Any] = (
        cast(dict[str, Any], json.loads(str(annexes[0]["data"]))) if annexes else {}
    )
    year = int(annexes[0]["year"]) if annexes else None
    body: dict[str, Any] = (
        cast(dict[str, Any], json.loads(str(snapshot["payload_json"])))
        if snapshot and snapshot["payload_json"]
        else {}
    )
    found = cast(list[dict[str, Any]], body.get("found") or [])
    company: dict[str, Any] = found[0] if found else {}
    contacts = cast(list[dict[str, Any]], client["contacts"])
    manager = next((item for item in contacts if item.get("role") == "energy_manager"), None)
    contact = next((item for item in contacts if item.get("role") == "contact"), None)
    person: dict[str, Any] | None = (
        {"name": contact["name"], "source": "client", "annex_year": None}
        if contact
        else {"name": latest["contact_person"], "source": "annex", "annex_year": year}
        if latest.get("contact_person")
        else None
    )
    return {
        "client": client,
        "identification": _identification(
            company, latest, year, str(snapshot["retrieved_at"]) if snapshot else None
        ),
        "fiscal": _fiscal(company),
        "energy_manager": manager,
        "contact_person": person,
        "memory": memory,
        "annexes": [
            {
                "sha": item["sha"],
                "year": item["year"],
                "file_name": cast(dict[str, Any], json.loads(str(item["data"]))).get("file_name")
                or item["original_name"],
                "read_at": item["read_at"],
            }
            for item in annexes
        ],
    }
