"""Confirmed client identifiers shared by future Ema workflows."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from ema.core.errors import EmaError
from ema.core.workspace import Workspace


@dataclass(frozen=True)
class KnownClient:
    legal_name: str
    tax_id: str | None
    job_id: str
    decision_id: str
    kind: str
    identifier: str


def _cui(value: str) -> str:
    return re.sub(r"\D", "", value)


def _active_rows(db: sqlite3.Connection, kind: str, identifier: str) -> list[KnownClient]:
    rows = db.execute(
        "SELECT m.* FROM client_memory m JOIN decisions d ON d.id=m.decision_id "
        "WHERE m.kind=? AND m.identifier=? AND json_extract(d.data,'$.undone_by') IS NULL",
        (kind, identifier),
    ).fetchall()
    return [
        KnownClient(
            str(row["legal_name"]),
            str(row["tax_id"]) if row["tax_id"] else None,
            str(row["job_id"]),
            str(row["decision_id"]),
            str(row["kind"]),
            str(row["identifier"]),
        )
        for row in rows
    ]


def find_by_cui(ws: Workspace, tax_id: str) -> list[KnownClient]:
    with ws.connect() as db:
        return _active_rows(db, "cui", _cui(tax_id))


def find_by_pod(ws: Workspace, pod: str) -> list[KnownClient]:
    with ws.connect() as db:
        return _active_rows(db, "pod", pod)


def check_conflicts(
    db: sqlite3.Connection, *, tax_id: str | None, pods: set[str], name: str
) -> None:
    for kind, identifier in [
        *(("pod", pod) for pod in pods),
        *([("cui", _cui(tax_id))] if tax_id else []),
    ]:
        for known in _active_rows(db, kind, identifier):
            if (tax_id and known.tax_id and _cui(known.tax_id) != _cui(tax_id)) or (
                kind == "cui" and known.legal_name.casefold() != name.casefold()
            ):
                raise EmaError(
                    "client_memory_conflict",
                    "Identitatea clientului intră în conflict cu memoria.",
                    f"{kind} confirmed in job {known.job_id}",
                )


def remember(
    db: sqlite3.Connection,
    *,
    name: str,
    tax_id: str | None,
    pods: set[str],
    job: str,
    decision_id: str,
) -> None:
    check_conflicts(db, tax_id=tax_id, pods=pods, name=name)
    for kind, identifier in [
        *(("pod", pod) for pod in pods),
        *([("cui", _cui(tax_id))] if tax_id else []),
    ]:
        db.execute(
            "INSERT INTO client_memory(kind,identifier,legal_name,tax_id,job_id,decision_id) "
            "VALUES (?,?,?,?,?,?)",
            (kind, identifier, name, tax_id, job, decision_id),
        )
