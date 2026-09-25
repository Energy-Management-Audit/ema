"""PIEE review projections from persisted fields and slot versions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ema.core.errors import EmaError
from ema.core.jobs import get_job
from ema.core.review import conflicts, fields
from ema.core.workspace import Workspace
from ema.core.workspace.conversion import active_version
from ema.energy_data.prelucrare import import_prelucrare


def _piee(ws: Workspace, job: str) -> dict[str, object]:
    record = get_job(ws, job)
    if record["type"] != "piee":
        raise EmaError("wrong_job_type", "Lucrarea nu este PIEE.", "")
    return record


def list_measures(ws: Workspace, job: str) -> list[dict[str, Any]]:
    _piee(ws, job)
    groups: dict[str, dict[str, Any]] = {}
    for field in fields(ws, job):
        parts = field.key.split(".")
        if len(parts) != 4 or parts[0] != "measure":
            continue
        measure_id = ".".join(parts[:3])
        item = groups.setdefault(
            measure_id,
            {
                "id": measure_id,
                "name": "",
                "origin": parts[1],
                "savings_mwh": None,
                "evidence_ids": [],
                "missing": [],
            },
        )
        if parts[3] == "description" and field.value is not None:
            item["name"] = str(field.value)
        if parts[3] == "savings_mwh" and field.value is not None:
            item["savings_mwh"] = float(field.value)
        item["evidence_ids"].extend(field.evidence)
        if field.presence != "found":
            item["missing"].append(field.key)
    return list(groups.values())


def data(ws: Workspace, job: str) -> dict[str, Any]:
    _piee(ws, job)
    carrier_fields: dict[str, dict[int, Any]] = defaultdict(dict)
    evidence: dict[str, list[str]] = defaultdict(list)
    missing: list[str] = []
    for field in fields(ws, job):
        if field.presence != "found":
            missing.append(field.key)
        parts = field.key.split(".")
        if len(parts) == 3 and parts[0] == "carrier" and parts[2].isdigit():
            converted = None
            if field.value is not None and field.unit in {"MWh", "kWh"}:
                converted = float(field.value) / (1000 if field.unit == "kWh" else 1)
            else:
                missing.append(field.key)
            carrier_fields[parts[1]][int(parts[2])] = converted
            evidence[parts[1]].extend(field.evidence)
    years = sorted({year for values in carrier_fields.values() for year in values})
    return {
        "years": years,
        "carriers": [
            {
                "carrier": carrier,
                "annual_mwh": [values.get(year) for year in years],
                "evidence_ids": evidence[carrier],
            }
            for carrier, values in sorted(carrier_fields.items())
        ],
        "conflicts": [field.id for field in conflicts(ws, job)],
        "missing": missing,
    }


def prelucrare_state(ws: Workspace, job: str) -> dict[str, Any]:
    record = _piee(ws, job)
    source = active_version(ws, job, "prelucrare")
    result: dict[str, Any] = {"authority": "none"}
    if source is not None:
        path = ws.file_path(str(record["client_slug"]), source.file_sha)
        imported = import_prelucrare(path)
        result["input"] = {"file_id": source.file_sha, "years": list(imported.dataset.years)}
        result["authority"] = "input_for_covered_years"
    with ws.connect() as db:
        row = db.execute(
            "SELECT id,seq FROM outputs WHERE job_id=? AND relative_path LIKE '%.xlsx' "
            "ORDER BY seq DESC LIMIT 1",
            (job,),
        ).fetchone()
    if row is not None:
        result["output"] = {"id": str(row["id"]), "version": int(row["seq"])}
        if source is None:
            result["authority"] = "generated"
    return result
