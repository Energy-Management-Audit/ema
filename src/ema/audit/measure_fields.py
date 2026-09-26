"""Cell evidence and review-field proposals for the measures form."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from ema.audit.measures_form import MeasureRow
from ema.core.review.fields import fields, mark_absent, propose
from ema.core.review.models import Cell, Derivation, Evidence, Field, FieldSpec, ValueType
from ema.core.workspace import Workspace
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import Derived
from ema.energy_data.source import Located


def _evidence(ws: Workspace, job: str, sha: str, key: str, source: Located) -> Evidence:
    evidence_id = hashlib.sha256(f"{sha}:{source.ref.a1}:{key}".encode()).hexdigest()
    with ws.connect() as db:
        old = db.execute(
            "SELECT data FROM evidence WHERE id=? AND job_id=?", (evidence_id, job)
        ).fetchone()
    return Evidence(
        id=evidence_id,
        provenance="document",
        file_sha=sha,
        locator=Cell(sheet=source.ref.sheet, ref=source.ref.a1.split("!", 1)[1]),
        method="form",
        retrieved_at=Evidence.model_validate_json(old["data"]).retrieved_at
        if old
        else datetime.now(UTC),
        quote=str(source.value),
        highlight="exact",
    )


def absent(ws: Workspace, job: str, spec: FieldSpec) -> Field:
    old = next((item for item in fields(ws, job) if item.key == spec.key), None)
    if old is not None and old.value is None and old.presence == "not_found":
        return old
    return mark_absent(ws, job, spec, "not_found")


def supplied(
    ws: Workspace, job: str, sha: str, spec: FieldSpec, source: Located | None, value: object = None
) -> Field:
    if source is None:
        return absent(ws, job, spec)
    actual = source.value if value is None else value
    if spec.value_type == "number":
        actual = Decimal(str(actual))
    return propose(
        ws, job, spec, actual, [_evidence(ws, job, sha, spec.key, source)], state="supplied"
    )


def calculated(ws: Workspace, job: str, key: str, result: Derived) -> Field:
    spec = FieldSpec(key=key, label=key, value_type="number", unit=result.unit, chapter="ch6")
    if result.value is None:
        return absent(ws, job, spec)
    derivation = Derivation(
        formula_id=result.formula_id,
        inputs=list(result.inputs),
        factor_version=result.factor_version or FACTORS_2026.version,
    )
    evidence = Evidence(
        id=hashlib.sha256(
            f"{key}:{result.value}:{derivation.model_dump_json()}".encode()
        ).hexdigest(),
        provenance="calculated",
        method="calc",
        retrieved_at=datetime.now(UTC),
        highlight="none",
        derivation=derivation,
    )
    with ws.connect() as db:
        old = db.execute(
            "SELECT data FROM evidence WHERE id=? AND job_id=?", (evidence.id, job)
        ).fetchone()
    if old:
        evidence = Evidence.model_validate_json(old["data"])
    return propose(
        ws,
        job,
        spec,
        Decimal(str(result.value)),
        [evidence],
        state="calculated",
        derivation=derivation,
    )


def supplied_row(
    ws: Workspace, job: str, sha: str, prefix: str, row: MeasureRow
) -> dict[str, Field]:
    entries: tuple[tuple[str, Located | None, ValueType, str | None, str | None], ...] = (
        ("title", row.title, "text", None, None),
        ("effect", row.effect, "text", None, None),
        ("carrier", row.carrier, "enum", None, row.carrier_value.value),
        ("saving_amount", row.saving_amount, "number", str(row.unit.value), None),
        ("investment_thousand_lei", row.investment, "number", "mii lei", None),
        ("cost_saving_thousand_lei", row.cost_saving, "number", "mii lei/an", None),
        ("cost_note", row.cost_note, "text", None, None),
    )
    result: dict[str, Field] = {}
    for name, source, value_type, unit, value in entries:
        spec = FieldSpec(
            key=prefix + name, label=prefix + name, value_type=value_type, unit=unit, chapter="ch6"
        )
        result[name] = supplied(ws, job, sha, spec, source, value)
    return result
