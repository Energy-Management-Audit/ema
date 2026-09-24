"""Deterministic audit Read stage: located workbook values become review fields."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ema.audit.catalogue import CATALOGUE
from ema.audit.sections import recompute_ready, record_applicability
from ema.consumption_analysis.analysis import Metric, resolve_value
from ema.core.review.fields import propose
from ema.core.review.models import Cell, Derivation, Evidence, Field, FieldSpec, Manual
from ema.core.workspace import Workspace
from ema.energy_data.anexa import parse_anexa
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import EnergyDataset, field_key
from ema.energy_data.necesar import parse_necesar_info, to_dataset
from ema.energy_data.necesar_model import NecesarInfo
from ema.energy_data.source import Located, normal


@dataclass(frozen=True)
class ReadResult:
    dataset: EnergyDataset
    fields: tuple[Field, ...]
    issues: tuple[str, ...]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    key: str,
    source: Located,
    sha: str,
    method: str,
    *,
    value_type: str | None = None,
    unit: str | None = None,
) -> Field:
    ref = source.ref
    evidence_id = hashlib.sha256(f"{sha}:{ref.a1}:{key}".encode()).hexdigest()
    with ws.connect() as db:
        previous = db.execute(
            "SELECT data FROM evidence WHERE id=? AND job_id=?", (evidence_id, job)
        ).fetchone()
    evidence = Evidence(
        id=evidence_id,
        file_sha=sha,
        locator=Cell(sheet=ref.sheet, ref=ref.a1.split("!", 1)[1]),
        method=method,  # type: ignore[arg-type]
        retrieved_at=(
            Evidence.model_validate_json(previous["data"]).retrieved_at
            if previous
            else datetime.now(UTC)
        ),
        quote=str(source.value),
        highlight="exact",
    )
    value = source.value
    if value_type is None:
        value_type = "number" if isinstance(value, int | float) else "text"
    if value_type == "number":
        value = Decimal(str(value))
    spec = FieldSpec(
        key=key,
        label=key,
        value_type=value_type,  # type: ignore[arg-type]
        unit=unit or source.unit,
        chapter="ch2" if key.startswith("audit.") else "ch4",
    )
    return propose(ws, job, spec, value, [evidence], state="supplied")


def _read_series(  # noqa: C901
    ws: Workspace, job: str, info: NecesarInfo, sha: str
) -> list[Field]:
    result: list[Field] = []
    for carrier, block in (*info.carriers.items(), *info.water.items()):
        for year, series in block.years.items():
            for month, source in enumerate(series.months, 1):
                if source is not None:
                    result.append(
                        _record(
                            ws,
                            job,
                            field_key("carrier", carrier.value, year, month),
                            source,
                            sha,
                            "questionnaire",
                        )
                    )
            if series.total is not None:
                result.append(
                    _record(
                        ws,
                        job,
                        field_key("carrier", carrier.value, year),
                        series.total,
                        sha,
                        "questionnaire",
                    )
                )
            if series.tep_total is not None:
                result.append(
                    _record(
                        ws,
                        job,
                        field_key("carrier_tep", carrier.value, year),
                        series.tep_total,
                        sha,
                        "questionnaire",
                    )
                )
    for item in info.production:
        name = normal(str(item.name.value)).replace(" ", "_")
        for year, series in item.years.items():
            for month, source in enumerate(series.months, 1):
                if source is not None:
                    result.append(
                        _record(
                            ws,
                            job,
                            field_key("production", name, year, month),
                            source,
                            sha,
                            "questionnaire",
                        )
                    )
            if series.total is not None:
                result.append(
                    _record(
                        ws,
                        job,
                        field_key("production", name, year),
                        series.total,
                        sha,
                        "questionnaire",
                    )
                )
    return result


def _read_details(ws: Workspace, job: str, info: NecesarInfo, sha: str) -> list[Field]:
    result: list[Field] = []
    if info.production:
        result.append(
            _record(ws, job, "audit.production", info.production[0].name, sha, "questionnaire")
        )
    for kind, years in info.economics.items():
        for year, source in years.items():
            key = (
                field_key("turnover", None, year)
                if kind == "turnover_lei"
                else field_key("energy_costs", None, year)
                if kind == "energy_costs_lei"
                else f"audit.economics.{kind}.{year}"
            )
            result.append(_record(ws, job, key, source, sha, "questionnaire"))
    for year, source in info.employees.items():
        result.append(_record(ws, job, f"audit.employees.{year}", source, sha, "questionnaire"))
    if info.employees:
        latest = max(info.employees)
        result.append(
            _record(ws, job, "audit.employees", info.employees[latest], sha, "questionnaire")
        )
    for table_name, table in info.tables.items():
        prefix = {
            "autovehicule": "fleet",
            "cladiri": "buildings",
        }.get(table_name, "equipment" if table_name.startswith("echipamente ") else table_name)
        for index, row in enumerate(table.rows, 1):
            for column, source in row.values.items():
                sheet = normal(table_name).replace(" ", "_")
                label = normal(column).replace(" ", "_")
                key = f"audit.{prefix}.{sheet}.{index}.{label}"
                result.append(_record(ws, job, key, source, sha, "questionnaire"))
    return result


def read_dossier(ws: Workspace, job: str, necesar: Path, anexa: Path | None = None) -> ReadResult:
    """Read source workbooks without an AI provider or a document engine."""
    info = parse_necesar_info(necesar)
    sha = _sha(necesar)
    result = [*_read_series(ws, job, info, sha), *_read_details(ws, job, info, sha)]
    issues = [issue.code for issue in info.issues]
    if anexa is not None:
        data = parse_anexa(anexa)
        anexa_sha = _sha(anexa)
        for name, source in data.identity.items():
            key = "audit.company_name" if name == "name" else f"audit.{name}"
            result.append(_record(ws, job, key, source, anexa_sha, "anexa"))
        issues.extend(issue.code for issue in data.issues)
    dataset = to_dataset(info)
    if Carrier.electricity_pv in dataset.carriers:
        issues.append("PV sections in audits taken from the PIEE pattern; confirm")
    for year in dataset.years[-1:]:
        total = resolve_value(dataset, FACTORS_2026, Metric("tep_total"), year)
        if total.value is None:
            issues.append(f"tep_class_missing:{year}")
            continue
        key = "audit.tep_class"
        evidence_id = hashlib.sha256(f"{sha}:{key}:{FACTORS_2026.version}".encode()).hexdigest()
        with ws.connect() as db:
            previous = db.execute(
                "SELECT data FROM evidence WHERE id=? AND job_id=?", (evidence_id, job)
            ).fetchone()
        evidence = Evidence(
            id=evidence_id,
            locator=Manual(who="ema", note="tep_total threshold from dataset"),
            method="calc",
            retrieved_at=(
                Evidence.model_validate_json(previous["data"]).retrieved_at
                if previous
                else datetime.now(UTC)
            ),
            highlight="none",
        )
        result.append(
            propose(
                ws,
                job,
                FieldSpec(
                    key=key, label=f"Pragul 1000 tep ({year})", value_type="enum", chapter="ch2"
                ),
                "at_least_1000_tep" if total.value >= 1000 else "below_1000_tep",
                [evidence],
                state="calculated",
                derivation=Derivation(
                    formula_id="tep_total_threshold_1000",
                    inputs=(
                        [field_key("carrier_tep", carrier.value, year) for carrier in info.carriers]
                        if total.origin == "filed"
                        else [
                            field_key("carrier", carrier.value, year) for carrier in info.carriers
                        ]
                    ),
                    factor_version="filed" if total.origin == "filed" else FACTORS_2026.version,
                ),
            )
        )
    recompute_ready(ws, job)
    for section in CATALOGUE:
        if section.id.startswith("ch4."):
            record_applicability(ws, job, section.id)
    return ReadResult(dataset, tuple(result), tuple(issues))
