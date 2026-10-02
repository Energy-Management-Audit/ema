"""Review items for the ch. 4 totals: a filed total that differs, a carrier filed but not read."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from ema.core.review.fields import mark_absent, propose
from ema.core.review.models import Cell, Derivation, Evidence, Field, FieldSpec, Issue, Manual
from ema.core.workspace import Workspace
from ema.energy_data.calc import tep, tep_total
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier, counts_in_total
from ema.energy_data.factors import FactorTable
from ema.energy_data.model import EnergyDataset, field_key

TOTAL_PREFIX = "tep_total."


def _evidence(ws: Workspace, job: str, evidence: Evidence) -> Evidence:
    """Keep the first retrieval time so reading the same dossier again changes nothing."""
    with ws.connect() as db:
        row = db.execute(
            "SELECT data FROM evidence WHERE id=? AND job_id=?", (evidence.id, job)
        ).fetchone()
    if row is None:
        return evidence
    return evidence.model_copy(
        update={"retrieved_at": Evidence.model_validate_json(row["data"]).retrieved_at}
    )


def _filed_evidence(ws: Workspace, job: str, sha: str, year: int, source: str) -> list[Evidence]:
    result: list[Evidence] = []
    for part in source.split("+"):
        sheet, ref = part.split("!", 1)
        digest = hashlib.sha256(f"{job}:{sha}:{part}:{TOTAL_PREFIX}{year}".encode()).hexdigest()
        result.append(
            _evidence(
                ws,
                job,
                Evidence(
                    id=digest,
                    provenance="document",
                    file_sha=sha,
                    locator=Cell(sheet=sheet, ref=ref),
                    method="questionnaire",
                    retrieved_at=datetime.now(UTC),
                    highlight="exact",
                ),
            )
        )
    return result


def record_totals_review(
    ws: Workspace, job: str, dataset: EnergyDataset, factors: FactorTable, sha: str
) -> list[str]:
    """Mark what the client filed but the readings do not back; returns the keys it raised."""
    raised: list[str] = []
    for year in dataset.years:
        carriers = [
            carrier
            for carrier in dataset.carriers
            if counts_in_total(carrier) and year in dataset.carriers[carrier]
        ]
        for carrier in carriers:
            filed = dataset.filed_indicators.get(f"tep.{carrier.value}", {}).get(year)
            derived = tep(dataset, factors, carrier, year)
            if (
                filed is None
                or derived.value is not None
                or all(item.startswith("factor.") for item in derived.missing)
            ):
                continue
            key = field_key("carrier", carrier.value, year)
            annual = dataset.carriers[carrier][year].annual
            spec = FieldSpec(
                key=key,
                label=CARRIER_NAMES_RO[carrier],
                value_type="number",
                unit=annual.unit if annual else "tep",
                chapter="ch4",
                required=True,
            )
            mark_absent(ws, job, spec, "not_found", only_if_missing=True)
            raised.append(key)
        total = tep_total(dataset, factors, year)
        filed_total = dataset.filed_indicators.get("tep_total", {}).get(year)
        if filed_total is None or total.value is None:
            continue
        if abs(total.value - filed_total.value) <= 0.5 * 10 ** (-filed_total.decimals) + 1e-12:
            continue
        spec = FieldSpec(
            key=f"{TOTAL_PREFIX}{year}",
            label=f"Totalul în tep pentru {year}",
            value_type="number",
            unit="tep",
            chapter="ch4",
            decimals=filed_total.decimals,
        )
        propose(
            ws,
            job,
            spec,
            Decimal(str(round(filed_total.value, filed_total.decimals))),
            _filed_evidence(ws, job, sha, year, filed_total.source),
            state="supplied",
        )
        digest = hashlib.sha256(f"{job}:{sha}:{spec.key}:{factors.version}".encode()).hexdigest()
        derivation = Derivation(
            formula_id="tep_total",
            inputs=[field_key("carrier", carrier.value, year) for carrier in carriers],
            factor_version=factors.version,
        )
        calculated = _evidence(
            ws,
            job,
            Evidence(
                id=digest,
                provenance="calculated",
                locator=Manual(who="ema", note="suma componentelor tipărite în capitolul 4"),
                method="calc",
                retrieved_at=datetime.now(UTC),
                highlight="none",
                derivation=derivation,
            ),
        )
        propose(
            ws,
            job,
            spec,
            Decimal(str(round(total.value, filed_total.decimals))),
            [calculated],
            state="calculated",
            derivation=derivation,
        )
        raised.append(spec.key)
    return raised


def totals_issues(facts: dict[str, Field]) -> list[Issue]:
    """Blocking issues for the final: an unresolved total conflict, a carrier read as missing."""
    issues: list[Issue] = []
    for key, field in sorted(facts.items()):
        parts = key.split(".")
        if key.startswith(TOTAL_PREFIX) and field.confidence == "conflict":
            issues.append(
                Issue(
                    code="conflict",
                    field_id=field.id,
                    message=(
                        f"Rezolvaţi conflictul: {field.label} depus diferă de suma componentelor"
                    ),
                )
            )
        elif (
            len(parts) == 3
            and parts[0] == "carrier"
            and parts[1] in Carrier._value2member_map_
            and field.required
            and field.presence == "not_found"
            and field.review != "accepted"
        ):
            carrier = Carrier(parts[1])
            issues.append(
                Issue(
                    code="carrier_incomplete",
                    field_id=field.id,
                    message=f"Lipseşte consumul de {CARRIER_NAMES_RO[carrier]} pentru {parts[2]}.",
                )
            )
    return issues
