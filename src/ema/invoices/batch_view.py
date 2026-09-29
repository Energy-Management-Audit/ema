"""HTTP projection of an invoice extraction batch."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from ema.core.workspace import Workspace
from ema.invoices.artifact import decode_draft
from ema.invoices.export.workbook_contract import summary_net_value
from ema.invoices.identity_review import batch_snapshot, resolve_snapshot
from ema.invoices.identity_view import identity_from_snapshot
from ema.invoices.months import invoice_month, missing_months
from ema.invoices.outliers import outliers


def _number(value: object) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def _invoice_date(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value)
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def _sources(fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for key in ("invoice_number", "active_energy", "active_energy_price"):
        evidence = cast("list[dict[str, Any]]", _field(fields, key).get("evidence") or [])
        if evidence:
            sources[key] = {
                "page": int(evidence[0]["page_number"]),
                "snippet": str(evidence[0]["snippet"]),
            }
    return sources


def _field(fields: dict[str, Any], key: str) -> dict[str, Any]:
    return cast("dict[str, Any]", fields.get(key) or {})


def batch_view(ws: Workspace, job: str) -> dict[str, Any]:
    snapshot = batch_snapshot(ws, job)
    identity = identity_from_snapshot(snapshot)
    rows: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for outcome in resolve_snapshot(snapshot):
        name = str(outcome["source_path"])
        slot = str(outcome["slot"] or "")
        if not outcome["drafts"]:
            files.append(
                {
                    "slot": slot,
                    "file_name": name,
                    "status": outcome["status"],
                    "reason": outcome.get("reason"),
                }
            )
            continue
        for index, draft in enumerate(outcome["drafts"]):
            fields = draft["fields"]
            consumption = _number(_field(fields, "active_energy").get("value"))
            price = _number(_field(fields, "active_energy_price").get("value"))
            value = summary_net_value(decode_draft(draft), "active_energy")
            rows.append(
                {
                    "id": hashlib.sha256(
                        f"{slot}:{index}:{draft['document_id']}".encode()
                    ).hexdigest()[:16],
                    "month": invoice_month(fields),
                    "consumption_kwh": consumption,
                    "source_evidence_ids": [],
                    "anomalies": [str(issue["code"]) for issue in draft["issues"] if issue["code"]],
                    "file_name": name,
                    "slot": slot,
                    "supplier": draft.get("supplier"),
                    "invoice_number": str(_field(fields, "invoice_number").get("value") or "")
                    or None,
                    "invoice_date": _invoice_date(_field(fields, "invoice_date").get("value")),
                    "status": outcome["status"],
                    "issues": [
                        str(issue["message"]) for issue in [*outcome["issues"], *draft["issues"]]
                    ],
                    "price_lei_kwh": price,
                    "value_lei": value,
                    "sources": _sources(fields),
                    "outlier": None,
                }
            )
    rows.sort(key=lambda row: (row["month"] is None, row["month"] or "", row["invoice_date"] or ""))
    eligible = [row for row in rows if row["status"] in {"exportable", "requires_review"}]
    monthly: dict[str, Decimal] = defaultdict(Decimal)
    for row in eligible:
        if row["month"] and row["consumption_kwh"] is not None:
            monthly[row["month"]] += row["consumption_kwh"]
    marked = outliers(monthly)
    for row in rows:
        if row["month"] in marked:
            ratio, mean = marked[row["month"]]
            row["outlier"] = {"ratio": ratio, "neighbours_mean_kwh": mean}
    years = Counter(row["month"][:4] for row in rows if row["month"])
    year = int(years.most_common(1)[0][0]) if years else None
    consumption_total = sum((row["consumption_kwh"] or Decimal(0) for row in eligible), Decimal(0))
    value_total = sum((row["value_lei"] or Decimal(0) for row in eligible), Decimal(0))
    return {
        "batch_id": identity["batch_id"],
        "identity": identity,
        "rows": rows,
        "missing_months": missing_months({row["month"] for row in rows if row["month"]}),
        "files": files,
        "totals": {
            "months": len(
                {
                    row["month"]
                    for row in rows
                    if row["month"] and row["month"].startswith(f"{year}-")
                }
            )
            if year
            else 0,
            "consumption_kwh": consumption_total,
            "value_lei": value_total,
            "price_avg_lei_kwh": value_total / consumption_total if consumption_total else None,
        },
        "year": year,
        "read_ended_at": snapshot.ended_at,
    }
