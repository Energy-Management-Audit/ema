"""Stable JSON form of an invoice extraction run."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, cast

from ema.invoices.configuration.field_catalog import FIELD_BY_ID, FieldKind
from ema.invoices.models import (
    EnergyCategory,
    FieldStatus,
    FieldValue,
    InvoiceDraft,
    IssueCode,
    IssueSeverity,
    PriceDetail,
    SourceEvidence,
    ValidationIssue,
)
from ema.invoices.outcomes import DocumentOutcome


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in cast(dict[str, Any], value).items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in cast(list[Any] | tuple[Any, ...], value)]
    if isinstance(value, Enum | Decimal | date | Path):
        return str(value)
    return value


def encode(outcomes: list[DocumentOutcome]) -> str:
    rows: list[dict[str, Any]] = []
    for outcome in outcomes:
        row = asdict(outcome)
        row["source_path"] = outcome.source_path.name
        rows.append(_json_value(row))
    return json.dumps(rows, ensure_ascii=False, sort_keys=True, indent=2)


def _evidence(rows: list[dict[str, Any]]) -> tuple[SourceEvidence, ...]:
    return tuple(SourceEvidence(**row) for row in rows)


def _scalar(key: str, value: Any) -> str | Decimal | date | int | None:
    if value is None or isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise ValueError("Invalid invoice field")
    kind = FIELD_BY_ID.get(key)
    if kind is not None and kind.kind is FieldKind.DECIMAL:
        return Decimal(value)
    if kind is not None and kind.kind is FieldKind.DATE:
        return date.fromisoformat(value)
    return value


def _draft(row: dict[str, Any]) -> InvoiceDraft:
    fields = {
        key: FieldValue(
            _scalar(key, value["value"]),
            FieldStatus(value["status"]),
            _evidence(value["evidence"]),
            value["message"],
        )
        for key, value in row["fields"].items()
    }
    details = [
        PriceDetail(
            EnergyCategory(detail["category"]),
            detail["description"],
            Decimal(detail["source_quantity"]),
            detail["source_unit"],
            Decimal(detail["source_unit_price"]),
            Decimal(detail["normalized_quantity"]),
            detail["normalized_unit"],
            Decimal(detail["normalized_unit_price"]),
            Decimal(detail["net_value"]),
            SourceEvidence(**detail["evidence"]),
        )
        for detail in row["price_details"]
    ]
    issues = [
        ValidationIssue(
            issue["field_id"],
            IssueSeverity(issue["severity"]),
            issue["message"],
            IssueCode(issue["code"]) if issue["code"] else None,
        )
        for issue in row["issues"]
    ]
    return InvoiceDraft(
        document_id=row["document_id"],
        source_filename=row["source_filename"],
        supplier=row["supplier"],
        fields=fields,
        price_details=details,
        issues=issues,
        metadata=row["metadata"],
    )


def exportable_drafts(payload: str) -> list[InvoiceDraft]:
    rows: list[dict[str, Any]] = json.loads(payload)
    return [
        _draft(draft) for row in rows if row["status"] == "exportable" for draft in row["drafts"]
    ]
