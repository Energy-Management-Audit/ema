"""Client registry identity and revision-safe edits."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from ema.core.errors import EmaError
from ema.core.workspace import Workspace

_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


def validate_id(client_id: str) -> str:
    if not _ID.fullmatch(client_id):
        raise EmaError("invalid_id", "Identificatorul clientului este invalid.", "")
    return client_id


def _view(row: Any) -> dict[str, Any]:
    result = dict(row)
    result["sites"] = json.loads(result.pop("sites_json"))
    result["contacts"] = json.loads(result.pop("contacts_json"))
    return result


def list_clients(ws: Workspace) -> list[dict[str, Any]]:
    with ws.connect() as db:
        rows = db.execute("SELECT * FROM clients ORDER BY name COLLATE NOCASE, id").fetchall()
    return [_view(row) for row in rows]


def get_client(ws: Workspace, client_id: str) -> dict[str, Any]:
    validate_id(client_id)
    with ws.connect() as db:
        row = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if row is None:
        raise EmaError("client_missing", "Clientul nu există.", "")
    return _view(row)


def create_client(ws: Workspace, name: str | None, cui: str | None = None) -> dict[str, Any]:
    client_id = uuid.uuid4().hex
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if cui and db.execute("SELECT 1 FROM clients WHERE cui=?", (cui,)).fetchone():
            raise EmaError("client_exists", "Clientul există deja.", "")
        db.execute("INSERT INTO clients(id,name,cui) VALUES (?,?,?)", (client_id, name, cui))
    return get_client(ws, client_id)


def update_client(
    ws: Workspace, client_id: str, patch: dict[str, Any], on_revision: int
) -> dict[str, Any]:
    validate_id(client_id)
    allowed = {"name", "cui", "caen", "sites", "contacts"}
    if patch.keys() - allowed:
        raise EmaError("invalid_id", "Datele clientului sunt invalide.", "")
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        if row is None:
            raise EmaError("client_missing", "Clientul nu există.", "")
        if row["revision"] != on_revision:
            raise EmaError("stale_revision", "Clientul a fost modificat.", "")
        current = _view(row)
        current.update(patch)
        db.execute(
            "UPDATE clients SET name=?,cui=?,caen=?,sites_json=?,contacts_json=?,"
            "revision=revision+1 WHERE id=?",
            (
                current["name"],
                current["cui"],
                current["caen"],
                json.dumps(current["sites"]),
                json.dumps(current["contacts"]),
                client_id,
            ),
        )
    return get_client(ws, client_id)


def list_sites(ws: Workspace, client_id: str) -> list[dict[str, Any]]:
    return get_client(ws, client_id)["sites"]


def list_contacts(ws: Workspace, client_id: str) -> list[dict[str, Any]]:
    return get_client(ws, client_id)["contacts"]
