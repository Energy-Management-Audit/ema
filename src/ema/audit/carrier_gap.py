"""The review message for a carrier that is used but has no quantity: it names the place."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping

from ema.audit.render_dataset import carrier_cost, quantity_empty
from ema.core.office.numbers_ro import format_number
from ema.core.review.models import Cell, Evidence, Field
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier
from ema.energy_data.model import CarrierSeries


def _place(db: sqlite3.Connection, job: str, fields: list[Field]) -> tuple[str, str, str] | None:
    """File name, sheet and cell of the first workbook cell that evidences one of the fields."""
    for field in fields:
        for evidence_id in field.evidence:
            row = db.execute(
                "SELECT e.data, (SELECT v.original_name FROM slot_versions v "
                "WHERE v.job_id=e.job_id AND v.file_sha=json_extract(e.data, '$.file_sha') "
                "AND v.original_name IS NOT NULL ORDER BY v.version DESC LIMIT 1) AS file_name "
                "FROM evidence e WHERE e.id=? AND e.job_id=?",
                (evidence_id, job),
            ).fetchone()
            if row is None or row["file_name"] is None:
                continue
            locator = Evidence.model_validate_json(row["data"]).locator
            if isinstance(locator, Cell):
                return str(row["file_name"]), locator.sheet, locator.ref
    return None


def blocked_message(
    db: sqlite3.Connection,
    job: str,
    fields: Mapping[str, Field],
    series: CarrierSeries,
    carrier: Carrier,
    year: int,
) -> str:
    name = CARRIER_NAMES_RO[carrier]
    base = f"Totalul de energie din {year} lipseşte: completaţi cantitatea de {name}."
    cost = carrier_cost(fields, carrier, year)
    if cost is None or not quantity_empty(series):
        return base
    prefix = f"carrier.{carrier.value}.{year}"
    quantity = [
        field
        for key, field in sorted(fields.items())
        if key == prefix or key.startswith(f"{prefix}.")
    ]
    where = _place(db, job, quantity)
    row = re.search(r"\d+", where[2]) if where else None
    gap = (
        f" în «{where[0]}», foaia «{where[1]}», rândul {row.group()} (lunile goale, total 0)"
        if where and row
        else ""
    )
    spent = f"{format_number(cost.value, cost.decimals)} lei"
    paid = _place(db, job, [cost])
    source = f" («{paid[0]}», foaia «{paid[1]}», celula {paid[2]})" if paid else ""
    return (
        f"Totalul de energie din {year} lipseşte: cantitatea de {name} nu este completată"
        f"{gap}; societatea are cheltuieli cu {name} de {spent} "
        f"în {year}{source}. Completaţi cantitatea din facturi sau marcaţi combustibilul "
        "ca neutilizat."
    )
