"""Record filed and calculated payback values in shared review."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from ema.core.review import propose
from ema.core.review.models import Cell, Derivation, Evidence, FieldSpec
from ema.core.workspace import Workspace
from ema.energy_data.anexa_cells import Measure
from ema.energy_data.source import Located
from ema.piee.measures import calculated_payback, payback_matches


def _source_evidence(value: Located, file_sha: str) -> Evidence:
    return Evidence(
        id=uuid.uuid4().hex,
        provenance="document",
        file_sha=file_sha,
        locator=Cell(sheet=value.ref.sheet, ref=value.ref.a1),
        method="anexa",
        retrieved_at=datetime.now(UTC),
        highlight="exact",
    )


def record_payback_check(
    ws: Workspace, job: str, kind: str, index: int, row: Measure, anexa_sha: str
) -> None:
    calculated = calculated_payback(row)
    key = f"measure.{kind}.{index}.payback_years"
    filed = row.values.get("payback_years")
    if calculated is None:
        if filed is not None:
            propose(
                ws,
                job,
                FieldSpec(key=key, label=key, value_type="number", unit="ani"),
                Decimal(str(filed.value)),
                [_source_evidence(filed, anexa_sha)],
                state="extracted",
            )
        return

    cost = row.values["investment_thousand_lei"]
    saving = row.values["saving_thousand_lei"]
    inputs = [
        f"measure.{kind}.{index}.{name}"
        for name in ("investment_thousand_lei", "saving_thousand_lei")
    ]
    derived = Derivation(
        formula_id="payback.cost_div_savings", inputs=inputs, factor_version="none"
    )
    evidence = [
        _source_evidence(cost, anexa_sha),
        _source_evidence(saving, anexa_sha),
        Evidence(
            id=uuid.uuid4().hex,
            provenance="calculated",
            locator=Cell(sheet="derived", ref=key),
            method="calc",
            retrieved_at=datetime.now(UTC),
            highlight="none",
            derivation=derived,
        ),
    ]
    result = Decimal(str(calculated))
    if filed is None:
        propose(
            ws,
            job,
            FieldSpec(
                key=key, label="Calculat, necompletat în anexă", value_type="number", unit="ani"
            ),
            result,
            evidence,
            state="calculated",
            derivation=derived,
        )
        return

    propose(
        ws,
        job,
        FieldSpec(
            key=key + ".calculated", label=key + " calculated", value_type="number", unit="ani"
        ),
        result,
        evidence,
        state="calculated",
        derivation=derived,
    )
    spec = FieldSpec(key=key, label=key, value_type="number", unit="ani")
    if not payback_matches(row, calculated):
        propose(ws, job, spec, result, evidence, state="calculated", derivation=derived)
    propose(
        ws,
        job,
        spec,
        Decimal(str(filed.value)),
        [_source_evidence(filed, anexa_sha)],
        state="extracted",
    )
