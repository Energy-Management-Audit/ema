"""ANAF lookup and client-bound snapshots."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, cast

from ema.clients.registry import create_client, get_client, update_client, validate_id
from ema.core import web
from ema.core.errors import EmaError
from ema.core.workspace import Workspace

ANAF_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"


def _lookup(cui: str) -> tuple[str, bytes, dict[str, Any]]:
    payload = json.dumps([{"cui": int(cui), "data": datetime.now(UTC).date().isoformat()}]).encode()
    try:
        url, content_type, body = web.fetch_bytes(
            ANAF_URL, method="POST", payload=payload, allowed_host="webservicesp.anaf.ro"
        )
        if content_type != "application/json":
            raise ValueError("content type")
        response = cast("dict[str, Any]", json.loads(body))
        found = response["found"]
        if not isinstance(found, list):
            raise ValueError("found")
        if not found:
            raise EmaError("anaf_missing", "Firma nu apare în registru.", "")
        company = cast("dict[str, Any]", found[0])
        general = cast("dict[str, Any]", company["date_generale"])
        if str(general["cui"]) != cui:
            raise ValueError("cui")
        return url, body, company
    except EmaError as exc:
        if exc.code == "anaf_missing":
            raise
        raise EmaError("anaf_unavailable", "Registrul ANAF nu este disponibil.", exc.code) from exc
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise EmaError("anaf_unavailable", "Răspunsul ANAF este invalid.", "") from exc


def _save_snapshot(ws: Workspace, client: dict[str, Any], url: str, body: bytes) -> dict[str, Any]:
    client_id = str(client["id"])
    retrieved_at = datetime.now(UTC).isoformat()
    sha = hashlib.sha256(body).hexdigest()
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT cui,revision FROM clients WHERE id=?", (client_id,)).fetchone()
        if current is None or (current["cui"], current["revision"]) != (
            client["cui"],
            client["revision"],
        ):
            raise EmaError("stale_revision", "Clientul a fost modificat.", client_id)
        db.execute(
            "INSERT INTO anaf_snapshots(client_id,status,retrieved_at,source_url,payload_json,sha) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(client_id) DO UPDATE SET "
            "status=excluded.status,retrieved_at=excluded.retrieved_at,"
            "source_url=excluded.source_url,payload_json=excluded.payload_json,sha=excluded.sha",
            (client_id, "complete", retrieved_at, url, body.decode(), sha),
        )
        db.execute("UPDATE clients SET anaf_refreshed_at=? WHERE id=?", (retrieved_at, client_id))
    return {
        "client_id": client_id,
        "status": "complete",
        "retrieved_at": retrieved_at,
        "source_url": url,
    }


def refresh(ws: Workspace, client_id: str) -> dict[str, Any]:
    validate_id(client_id)
    client = get_client(ws, client_id)
    cui = re.sub(r"\D", "", str(client["cui"] or ""))
    if not cui.isdecimal() or not 2 <= len(cui) <= 10:
        raise EmaError("anaf_unavailable", "Codul fiscal nu poate fi verificat.", "")
    url, body, _ = _lookup(cui)
    return _save_snapshot(ws, client, url, body)


def create_from_anaf(ws: Workspace, cui: str) -> dict[str, Any]:
    digits = re.sub(r"\D", "", cui)
    if not 2 <= len(digits) <= 10:
        raise EmaError("invalid_id", "Codul fiscal este invalid.", "")
    with ws.connect() as db:
        rows = db.execute("SELECT cui FROM clients WHERE cui IS NOT NULL").fetchall()
    if any(re.sub(r"\D", "", str(row["cui"])) == digits for row in rows):
        raise EmaError("client_exists", "Clientul există deja.", "")
    url, body, company = _lookup(digits)
    general = company["date_generale"]
    name = general.get("denumire")
    if not isinstance(name, str) or not name.strip():
        raise EmaError("anaf_unavailable", "Răspunsul ANAF este invalid.", "")
    client = create_client(ws, name.strip(), digits)
    if general.get("cod_CAEN"):
        client = update_client(
            ws, str(client["id"]), {"caen": str(general["cod_CAEN"])}, int(client["revision"])
        )
    _save_snapshot(ws, client, url, body)
    return get_client(ws, str(client["id"]))
