"""Job-free ANAF lookup with a client-bound snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, cast

from ema.clients.registry import get_client, validate_id
from ema.core import web
from ema.core.errors import EmaError
from ema.core.workspace import Workspace

ANAF_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"


def refresh(ws: Workspace, client_id: str) -> dict[str, Any]:  # noqa: C901
    validate_id(client_id)
    client = get_client(ws, client_id)
    cui = re.sub(r"^RO", "", str(client["cui"] or "").strip(), flags=re.IGNORECASE)
    if not cui.isdecimal() or not 2 <= len(cui) <= 10:
        raise EmaError("anaf_unavailable", "Codul fiscal nu poate fi verificat.", "")
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
        for key in ("denumire", "cod_CAEN", "adresa", "nrRegCom"):
            general.get(key)
        social = cast("dict[str, Any]", company.get("adresa_sediu_social") or {})
        for key in ("sdenumire_Localitate", "sdenumire_Judet"):
            social.get(key)
    except EmaError as exc:
        if exc.code == "anaf_missing":
            raise
        raise EmaError("anaf_unavailable", "Registrul ANAF nu este disponibil.", exc.code) from exc
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise EmaError("anaf_unavailable", "Răspunsul ANAF este invalid.", "") from exc
    retrieved_at = datetime.now(UTC).isoformat()
    sha = hashlib.sha256(body).hexdigest()
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
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
