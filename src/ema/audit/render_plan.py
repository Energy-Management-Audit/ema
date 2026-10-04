"""The unit plan of an audit job: which repeated units its base keeps."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ema.audit.base_units import UnitPlan
from ema.audit.process_units import ProcessesSource, dossier_units
from ema.audit.visit import visit_view_from_slots
from ema.core.errors import EmaError
from ema.core.jobs import StageContext
from ema.core.jobs.reads import revision
from ema.core.review.models import Field
from ema.core.workspace import SlotVersion, Workspace
from ema.energy_data.carriers import WATER_CARRIERS, Carrier
from ema.energy_data.necesar import parse_necesar_info

_FAMILIES: dict[Carrier, str] = {
    Carrier.electricity_grid: "electricity",
    Carrier.electricity_pv: "electricity",
    Carrier.natural_gas: "gas",
    Carrier.diesel: "fuel",
    Carrier.petrol: "fuel",
    Carrier.lpg: "fuel",
    Carrier.fuel_oil: "fuel",
    Carrier.clu: "fuel",
    **dict.fromkeys(WATER_CARRIERS, "water"),
}


@dataclass(frozen=True)
class JobUnitPlan(UnitPlan):
    processes_source: ProcessesSource = "default"
    client_revision: tuple[str, int] | None = None


def carrier_families(job_fields: Iterable[Field]) -> frozenset[str]:
    families: set[str] = set()
    for field in job_fields:
        parts = field.key.split(".")
        if parts[0] != "carrier" or field.presence != "found" or len(parts) < 3:
            continue
        carrier = Carrier._value2member_map_.get(parts[1])
        if isinstance(carrier, Carrier) and carrier in _FAMILIES:
            families.add(_FAMILIES[carrier])
    return frozenset(families)


def _slot(row: dict[str, object]) -> SlotVersion:
    return SlotVersion(
        str(row["job_id"]),
        str(row["slot"]),
        int(str(row["version"])),
        str(row["file_sha"]),
        str(row["origin"]),
        None if row["converted_from"] is None else str(row["converted_from"]),
        None if row["original_name"] is None else str(row["original_name"]),
    )


def unit_plan(
    ws: Workspace,
    job: str,
    *,
    db: sqlite3.Connection | None = None,
    ctx: StageContext | None = None,
) -> JobUnitPlan:
    if db is None:
        with ws.connect() as connection:
            connection.execute("BEGIN")
            return unit_plan(ws, job, db=connection, ctx=ctx)
    record = db.execute(
        "SELECT j.client_slug, c.name, c.revision FROM jobs j "
        "LEFT JOIN clients c ON c.id=j.client_slug "
        "WHERE j.id=?",
        (job,),
    ).fetchone()
    job_fields = [
        Field.model_validate_json(row["data"])
        for row in db.execute("SELECT data FROM fields WHERE job_id=?", (job,))
    ]
    rows = db.execute(
        "SELECT v.*, f.relative_path, f.added_at FROM slots s JOIN slot_versions v "
        "ON v.job_id=s.job_id AND v.slot=s.name AND v.version=s.active_version "
        "JOIN jobs j ON j.id=s.job_id "
        "LEFT JOIN files f ON f.sha=v.file_sha AND f.client_slug=j.client_slug "
        "WHERE s.job_id=? ORDER BY s.name",
        (job,),
    ).fetchall()
    by_key = {field.key: field for field in job_fields}
    company = by_key.get("audit.company_name")
    client_name = (
        str(company.value).strip()
        if company and company.value and company.review != "rejected"
        else ""
    )
    client_revision = None
    if not client_name and record is not None:
        client_revision = (str(record["client_slug"]), int(record["revision"]))
        if ctx is not None:
            ctx.record_read("clients", *client_revision)
        client_name = str(record["name"] or "").strip()
    if not client_name:
        raise EmaError("audit_client_name", "Denumirea clientului lipseşte.", "")
    if ctx is not None:
        for key, field in by_key.items():
            ctx.record_read("fields.key", f"{job}:{key}", field.revision)
        ctx.record_read(
            "fields.key",
            f"{job}:audit.company_name",
            by_key["audit.company_name"].revision if "audit.company_name" in by_key else 0,
        )
        ctx.record_read(
            "slots.collection", f"{job}:", revision(db, "slots.collection", f"{job}:") or 0
        )
        for row in rows:
            ctx.record_read(
                "slots", f"{job}:{row['slot']}", revision(db, "slots", f"{job}:{row['slot']}") or 0
            )
    dossier = [row for row in rows if str(row["slot"]).startswith("dossier/")]
    processes = dossier_units(ws, [dict(row) for row in dossier])
    view = visit_view_from_slots([_slot(dict(row)) for row in rows])
    checklist = [row for row in dossier if Path(str(row["slot"])).name.startswith("0.")]
    tables = 0
    if len(checklist) == 1 and checklist[0]["relative_path"] is not None:
        info = parse_necesar_info(ws.path(str(checklist[0]["relative_path"])))
        tables = sum(name.startswith("echipamente ") for name in info.tables)
    count = by_key.get("audit_measure.count")
    measures = int(count.value) if count is not None and count.value is not None else 0
    return JobUnitPlan(
        client_name=client_name,
        processes=processes.count,
        carriers=carrier_families(job_fields),
        measured_panels=len(view.panels),
        thermal_measurements=any(str(row["slot"]).startswith("visit/thermal/") for row in rows),
        equipment_tables=tables,
        measures=measures,
        processes_source=processes.source,
        client_revision=client_revision,
    )
