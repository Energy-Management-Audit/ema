"""Confirm a batch identity and apply it to exportable invoice drafts."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ema.clients import remember
from ema.core.errors import EmaError
from ema.core.jobs import JobId, latest_ready_run
from ema.core.review import fields, undo
from ema.core.review.fields import decide_in_connection
from ema.core.review.models import Decision, Field
from ema.core.workspace import Workspace
from ema.invoices.batch_identity import KEY, BatchClient, proposal
from ema.invoices.models import normalize_client_name, normalize_client_tax_id


@dataclass(frozen=True)
class InvoiceReadiness:
    final_ok: bool
    blocking: tuple[str, ...]
    exportable: int
    omitted: tuple[str, ...]


def _artifact(ws: Workspace, job: JobId) -> Path:
    run = latest_ready_run(ws, job, "invoices")
    if run is None:
        raise EmaError("invoices_missing", "Extracția facturilor lipsește.", job)
    with ws.connect() as db:
        return ws.artifact_dir(db, job, "invoices", run) / "outcomes.json"


def raw_outcomes(ws: Workspace, job: JobId) -> list[dict[str, Any]]:
    return json.loads(_artifact(ws, job).read_text(encoding="utf-8"))


def batch_client(ws: Workspace, job: JobId) -> tuple[Field, BatchClient | None]:
    field = proposal(ws, job, raw_outcomes(ws, job))
    return field, BatchClient.from_field(field) if field.value is not None else None


def confirm_client(ws: Workspace, job: JobId) -> Decision:
    field, client = batch_client(ws, job)
    if client is None:
        raise EmaError("client_missing", "Clientul lotului nu a fost identificat.", job)
    if field.review in {"accepted", "corrected"}:
        raise EmaError("client_confirmed", "Clientul lotului este deja confirmat.", job)
    rows = raw_outcomes(ws, job)
    admissible_pods = _admissible_pods(rows, client)
    with ws.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        decision = decide_in_connection(db, job, field.id, field.revision, "user")
        remember(
            db,
            name=client.name,
            tax_id=client.tax_id,
            pods=admissible_pods,
            job=job,
            decision_id=decision.id,
        )
    return decision


def _admissible_pods(rows: list[dict[str, Any]], client: BatchClient) -> set[str]:
    """Remember only PODs printed on invoices compatible with the confirmed identity."""
    pods: set[str] = set()
    for row in rows:
        if row["status"] in {"failed", "incompatible", "duplicate", "unsupported"}:
            continue
        for draft in row["drafts"]:
            name_field = draft["fields"].get("client_name")
            tax_field = draft["fields"].get("client_tax_id")
            if name_field is None or not _matches_name(name_field, client.name):
                continue
            if (
                client.tax_id
                and tax_field
                and tax_field.get("value")
                and normalize_client_tax_id(tax_field["value"])
                != normalize_client_tax_id(client.tax_id)
            ):
                continue
            pod_field = draft["fields"].get("location_identifier")
            if pod_field and pod_field.get("value"):
                pods.add(str(pod_field["value"]))
    return pods


def undo_client(ws: Workspace, job: JobId, decision_id: str) -> Decision:
    field = next((item for item in fields(ws, job) if item.key == KEY), None)
    if field is None:
        raise EmaError("client_missing", "Clientul lotului nu a fost identificat.", job)
    with ws.connect() as db:
        row = db.execute(
            "SELECT 1 FROM decisions WHERE id=? AND job_id=? AND field_id=?",
            (decision_id, job, field.id),
        ).fetchone()
    if row is None:
        raise EmaError(
            "client_decision_missing", "Decizia clientului lotului lipsește.", decision_id
        )
    return undo(ws, job, decision_id, "user")


def _matches_name(field: dict[str, Any], name: str) -> bool:
    if field.get("status") in {"missing", "not_provided"}:
        return True
    expected = normalize_client_name(name)
    if expected is None:
        return False
    if normalize_client_name(field.get("value")) == expected:
        return True
    return field.get("status") == "ambiguous" and any(
        normalize_client_name(item["snippet"].split(":", 1)[-1].strip()) == expected
        for item in field["evidence"]
    )


def _approved(value: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {"value": value, "status": "approved", "evidence": evidence, "message": None}


def resolved_outcomes(ws: Workspace, job: JobId) -> list[dict[str, Any]]:
    rows = copy.deepcopy(raw_outcomes(ws, job))
    field, client = batch_client(ws, job)
    if client is None or field.review not in {"accepted", "corrected"}:
        return rows
    fills = {
        (item["supplier"], filename): item for item in client.pod_fill for filename in item["files"]
    }
    decision_id = _decision_id(ws, job)
    for row in rows:
        if row["status"] in {"failed", "incompatible", "duplicate", "unsupported"}:
            continue
        for draft in row["drafts"]:
            values = draft["fields"]
            name_field = values.get("client_name")
            tax_field = values.get("client_tax_id")
            if name_field is None:
                continue
            if not _matches_name(name_field, client.name) or (
                client.tax_id
                and tax_field
                and tax_field.get("value")
                and normalize_client_tax_id(tax_field["value"])
                != normalize_client_tax_id(client.tax_id)
            ):
                draft["issues"].append(
                    {
                        "field_id": "client_name",
                        "severity": "error",
                        "message": "Identitatea tipărită contrazice clientul confirmat al lotului.",
                        "code": "CONFLICTING_INVOICE",
                    }
                )
                continue
            values["client_name"] = _approved(client.name, name_field["evidence"])
            if client.tax_id and tax_field is not None:
                values["client_tax_id"] = _approved(client.tax_id, tax_field["evidence"])
            draft["issues"] = [
                issue
                for issue in draft["issues"]
                if issue["field_id"] not in {"client_name", "client_tax_id"}
            ]
            fill = fills.get((draft["supplier"], row["source_path"]))
            pod_field = values.get("location_identifier")
            if fill and pod_field and not pod_field.get("value"):
                source_evidence = [
                    {
                        "page_number": item["page"],
                        "snippet": f"{item['file']}: {item['snippet']}",
                        "label": "POD from confirmed batch identity",
                    }
                    for item in fill["sources"]
                ]
                values["location_identifier"] = _approved(fill["pod"], source_evidence)
                draft["issues"] = [
                    issue for issue in draft["issues"] if issue["field_id"] != "location_identifier"
                ]
                draft["metadata"]["pod_confirmation_decision"] = decision_id
            draft["metadata"]["client_confirmation_decision"] = decision_id
        if (
            row["drafts"]
            and all(
                not any(
                    value["status"] in {"missing", "ambiguous", "invalid"}
                    for value in draft["fields"].values()
                )
                and not any(issue["severity"] == "error" for issue in draft["issues"])
                for draft in row["drafts"]
            )
            and not any(issue["severity"] == "error" for issue in row["issues"])
        ):
            row["status"] = "exportable"
            row["reason"] = None
        else:
            row["status"] = "requires_review"
    return rows


def _decision_id(ws: Workspace, job: JobId) -> str:
    with ws.connect() as db:
        row = db.execute(
            "SELECT d.id FROM decisions d JOIN fields f ON f.id=d.field_id "
            "WHERE d.job_id=? AND f.key=? AND json_extract(d.data,'$.undone_by') IS NULL "
            "ORDER BY d.seq DESC LIMIT 1",
            (job, KEY),
        ).fetchone()
    return str(row["id"]) if row else ""


def readiness(ws: Workspace, job: JobId) -> InvoiceReadiness:
    field, _ = batch_client(ws, job)
    if field.review not in {"accepted", "corrected"}:
        return InvoiceReadiness(False, ("Clientul lotului nu este confirmat.",), 0, ())
    rows = resolved_outcomes(ws, job)
    exportable = sum(row["status"] == "exportable" for row in rows)
    omitted = tuple(str(row["source_path"]) for row in rows if row["status"] != "exportable")
    return InvoiceReadiness(
        bool(exportable),
        () if exportable else ("Nicio factură nu poate fi exportată.",),
        exportable,
        omitted,
    )
