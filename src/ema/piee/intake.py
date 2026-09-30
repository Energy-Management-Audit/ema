"""PIEE job intake with source locations and shared field review."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from ema.core.jobs import create_job
from ema.core.review import mark_absent, propose
from ema.core.review.models import Cell, Derivation, Evidence, FieldSpec
from ema.core.workspace import Workspace
from ema.energy_data.calc import tep_total
from ema.energy_data.carriers import Carrier
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.model import Reading
from ema.energy_data.source import Located
from ema.piee.dataset import PieeData, SourceDisagreement, load
from ema.piee.payback_review import record_payback_check


@dataclass(frozen=True)
class PieeJob:
    id: str
    data: PieeData


Method = Literal["questionnaire", "anexa", "prelucrare", "calc"]


def _evidence(location: Located | None, file_sha: str | None, method: Method, key: str) -> Evidence:
    calculated = method == "calc"
    if not calculated and (location is None or file_sha is None):
        raise ValueError(f"document evidence lacks a located source: {key}")
    return Evidence(
        id=uuid.uuid4().hex,
        provenance="calculated" if calculated else "document",
        file_sha=None if calculated else file_sha,
        locator=Cell(
            sheet=location.ref.sheet if location is not None else "derived",
            ref=location.ref.a1 if location is not None else key,
        ),
        method="calc" if calculated else method,
        retrieved_at=datetime.now(UTC),
        highlight="exact" if location is not None else "none",
        derivation=(
            Derivation(
                formula_id=key,
                inputs=[location.ref.a1] if location is not None else [],
                factor_version=FACTORS_2026.version,
            )
            if calculated
            else None
        ),
    )


def _sha(path: Path | None) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path is not None else None


def _method(source: str) -> Method:
    if source.startswith("prelucrare"):
        return "prelucrare"
    if source == "anexa":
        return "anexa"
    if source in {"calculated", "carrier_sum"}:
        return "calc"
    return "questionnaire"


def _file(source: str, shas: dict[str, str | None]) -> str | None:
    return shas.get(_method(source))


def _record_disagreement(
    ws: Workspace, job: str, item: SourceDisagreement, shas: dict[str, str | None]
) -> None:
    if item.chosen.value is None or item.alternative.value is None:
        raise ValueError("review disagreement requires two present values")
    unit_conflict = (
        item.chosen.value == item.alternative.value and item.chosen.unit != item.alternative.unit
    )
    spec = (
        FieldSpec(key=item.key + ".unit", label=item.key + " unit", value_type="text")
        if unit_conflict
        else FieldSpec(key=item.key, label=item.key, value_type="number", unit=item.chosen.unit)
    )
    alternative = item.alternative.unit if unit_conflict else Decimal(str(item.alternative.value))
    chosen = item.chosen.unit if unit_conflict else Decimal(str(item.chosen.value))
    propose(
        ws,
        job,
        spec,
        alternative,
        [
            _evidence(
                item.alternative_location,
                _file(item.alternative_source, shas),
                _method(item.alternative_source),
                item.key,
            )
        ],
        state="extracted",
    )
    propose(
        ws,
        job,
        spec,
        chosen,
        [
            _evidence(
                item.chosen_location,
                _file(item.chosen_source, shas),
                _method(item.chosen_source),
                item.key,
            )
        ],
        state="extracted",
    )


def _record_identity(ws: Workspace, job: str, data: PieeData, anexa_sha: str) -> None:
    for key, found in data.anexa.identity.items():
        share = key in {"site_1_production_share", "site_2_production_share"}
        propose(
            ws,
            job,
            FieldSpec(
                key=f"identity.{key}",
                label=key,
                value_type="number" if share else "text",
                unit="%" if share else None,
                required=key == "name",
            ),
            Decimal(str(found.value)) if share else str(found.value),
            [_evidence(found, anexa_sha, "anexa", key)],
            state="extracted",
        )
    if "site_2_name" in data.anexa.identity:
        for index in (1, 2):
            for name, unit in (("address", None), ("production_share", "%")):
                if (key := f"site_{index}_{name}") not in data.anexa.identity:
                    mark_absent(
                        ws,
                        job,
                        FieldSpec(
                            key=f"identity.{key}",
                            label=key,
                            value_type="number" if unit else "text",
                            unit=unit,
                        ),
                        "not_found",
                    )
    for issue in data.anexa.issues:
        if issue.code == "ownership_flag" and issue.detail not in data.anexa.identity:
            mark_absent(
                ws,
                job,
                FieldSpec(
                    key=f"identity.{issue.detail}",
                    label=issue.detail,
                    value_type="text",
                    required=True,
                ),
                "not_found",
            )
    if "registrul_comertului" not in data.anexa.identity:
        mark_absent(
            ws,
            job,
            FieldSpec(
                key="identity.registrul_comertului", label="Registrul Comerțului", value_type="text"
            ),
            "not_found",
        )


# A measure lacking one of these can still be completed by hand; each becomes a fillable field.
_MEASURE_COLUMNS: tuple[tuple[str, Literal["number", "year"], str | None], ...] = (
    ("investment_thousand_lei", "number", "mii lei"),
    ("saving_mwh", "number", "MWh"),
    ("commissioning_year", "year", None),
)


def _record_measures(ws: Workspace, job: str, data: PieeData, anexa_sha: str) -> None:
    groups = (
        ("audit", data.anexa.audit_measures),
        ("existing", data.anexa.existing_measures),
        ("planned", data.anexa.planned_measures),
    )
    for kind, rows in groups:
        for index, row in enumerate(rows, 1):
            values = {"description": row.description, **row.values}
            if row.commissioning_year is not None:
                values["commissioning_year"] = row.commissioning_year
            if row.location is not None:
                values["location"] = row.location
            for name, found in values.items():
                if name == "payback_years":
                    continue
                key = f"measure.{kind}.{index}.{name}"
                numeric = isinstance(found.value, int | float)
                propose(
                    ws,
                    job,
                    FieldSpec(
                        key=key,
                        label=key,
                        value_type="number" if numeric else "text",
                        unit=found.unit,
                    ),
                    Decimal(str(found.value)) if numeric else str(found.value),
                    [_evidence(found, anexa_sha, "anexa", key)],
                    state="extracted",
                )
            for name, value_type, unit in _MEASURE_COLUMNS:
                if name not in values:
                    key = f"measure.{kind}.{index}.{name}"
                    spec = FieldSpec(key=key, label=key, value_type=value_type, unit=unit)
                    mark_absent(ws, job, spec, "not_found")
            record_payback_check(ws, job, kind, index, row, anexa_sha)


def _locations(data: PieeData) -> dict[str, tuple[Located, Method]]:
    selected: dict[str, tuple[Located, Method]] = {}
    for carrier, block in data.necesar.carriers.items():
        for year, values in block.years.items():
            if values.total is not None:
                selected[f"carrier.{carrier.value}.{year}"] = (values.total, "questionnaire")
            for month, value in enumerate(values.months, 1):
                if value is not None:
                    selected[f"carrier.{carrier.value}.{year}.{month:02d}"] = (
                        value,
                        "questionnaire",
                    )
    for carrier in Carrier:
        for suffix in ("raw", "mwh", "gcal"):
            found = data.anexa.annual.get(f"{carrier.value}_{suffix}")
            if found is not None:
                selected.setdefault(f"carrier.{carrier.value}.{data.year}", (found, "anexa"))
    if data.prelucrare is not None:
        selected.update(
            (key, (value, "prelucrare")) for key, value in data.prelucrare.located.items()
        )
    return selected


def _record_dataset(ws: Workspace, job: str, data: PieeData, shas: dict[str, str | None]) -> None:
    locations = _locations(data)
    for carrier, years in data.dataset.carriers.items():
        for year, series in years.items():
            readings = [(f"carrier.{carrier.value}.{year}", series.annual)]
            readings.extend(
                (f"carrier.{carrier.value}.{year}.{month:02d}", reading)
                for month, reading in series.months.items()
            )
            for key, reading in readings:
                if reading is None or reading.value is None:
                    continue
                found = locations.get(key)
                if found is None:
                    mark_absent(
                        ws,
                        job,
                        FieldSpec(key=key, label=key, value_type="number", unit=reading.unit),
                        "failed",
                        "Source location missing for imported value",
                    )
                    continue
                location, method = found
                propose(
                    ws,
                    job,
                    FieldSpec(key=key, label=key, value_type="number", unit=reading.unit),
                    Decimal(str(reading.value)),
                    [_evidence(location, shas[method], method, key)],
                    state="extracted",
                )


def _record_annual(ws: Workspace, job: str, data: PieeData, shas: dict[str, str | None]) -> None:
    filed = data.annual_check.filed
    if filed is None or not isinstance(filed.value, int | float):
        mark_absent(
            ws,
            job,
            FieldSpec(
                key="annual.total_tep",
                label="Date anuale total tep",
                value_type="number",
                required=True,
            ),
            "not_found",
        )
        return
    chosen = data.prelucrare.filed.get(f"tep.total.{data.year}") if data.prelucrare else None
    spec = FieldSpec(
        key="annual.total_tep",
        label="Date anuale total tep",
        value_type="number",
        unit="tep",
        required=True,
    )
    propose(
        ws,
        job,
        spec,
        Decimal(str(filed.value)),
        [_evidence(filed, shas["anexa"], "anexa", spec.key)],
        state="extracted",
    )
    if chosen is not None and isinstance(chosen.value, int | float):
        propose(
            ws,
            job,
            spec,
            Decimal(str(chosen.value)),
            [_evidence(chosen, shas["prelucrare"], "prelucrare", spec.key)],
            state="extracted",
        )
    if data.annual_check.status == "conflict" and chosen is None:
        calculated = tep_total(data.dataset, data.factors, data.year)
        if calculated.value is not None:
            _record_disagreement(
                ws,
                job,
                SourceDisagreement(
                    spec.key,
                    Reading(calculated.value, "tep"),
                    Reading(float(filed.value), "tep"),
                    "calculated",
                    "anexa",
                    None,
                    filed,
                ),
                shas,
            )


def import_piee(  # noqa: PLR0913
    ws: Workspace,
    client_slug: str,
    year: int,
    anexa: Path,
    necesar: Path | None,
    prelucrare: Path | None = None,
    *,
    previous_piee: Path | None = None,
) -> PieeJob:
    """Validate sources before creating a job, then retain slot versions and review evidence."""
    load(year, anexa, necesar, prelucrare, previous_piee)
    job = create_job(ws, "piee", client_slug, year + 1)
    paths = {
        "anexa": anexa,
        "questionnaire": necesar,
        "prelucrare": prelucrare,
        "previous_piee": previous_piee,
    }
    for name, path in paths.items():
        if path is not None:
            ws.set_slot(job, name, ws.add_file(client_slug, path))
    return import_piee_into_job(
        ws, job, year, anexa, necesar, prelucrare, previous_piee=previous_piee
    )


def import_piee_into_job(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    year: int,
    anexa: Path,
    necesar: Path | None,
    prelucrare: Path | None = None,
    *,
    previous_piee: Path | None = None,
) -> PieeJob:
    """Reconcile immutable slot sources into an existing PIEE job."""
    data = load(year, anexa, necesar, prelucrare, previous_piee)
    paths = {
        "anexa": anexa,
        "questionnaire": necesar,
        "prelucrare": prelucrare,
        "previous_piee": previous_piee,
    }
    shas = {name: _sha(path) for name, path in paths.items()}
    if shas["anexa"] is None:
        raise ValueError("Anexa checksum missing")
    _record_identity(ws, job, data, shas["anexa"])
    _record_measures(ws, job, data, shas["anexa"])
    _record_dataset(ws, job, data, shas)
    _record_annual(ws, job, data, shas)
    for item in data.disagreements:
        _record_disagreement(ws, job, item, shas)
    return PieeJob(job, data)
