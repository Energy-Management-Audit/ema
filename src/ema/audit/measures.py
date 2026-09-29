"""Deterministic measures stage shared by the API, CLI and MCP."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from ema.audit.catalogue_labels import field_label
from ema.audit.catalogue_types import MaterialKind
from ema.audit.chapter_six import ChapterSixPlan, PlannedMeasure
from ema.audit.measure_fields import absent, calculated, supplied, supplied_row
from ema.audit.measures_form import MeasureRow, MeasuresForm, read_measures_form
from ema.audit.publication import queue_sections
from ema.audit.sections import (
    recompute_ready,
    record_material,
    refresh_staleness,
)
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, get_job, run_stage, status, subscribe
from ema.core.office.errors import OfficeError
from ema.core.review.fields import fields
from ema.core.review.models import FieldSpec
from ema.core.workspace import Workspace
from ema.core.workspace.conversion import active_version
from ema.energy_data.factors import FACTORS_2026
from ema.energy_data.measure_calc import measure_co2, measure_tep, payback_years


@dataclass(frozen=True)
class MeasuresResult:
    job: str
    run: str
    measures: int
    payback_missing: int
    factor_version: str
    missing_narratives: int
    plan_path: Path


def _form_path(ws: Workspace, job: str) -> Path:
    record = get_job(ws, job)
    if record["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    slot = active_version(ws, job, "measures")
    if slot is None:
        raise EmaError("measures_form_missing", "Formularul „Măsuri propuse” lipseşte.", job)
    return ws.file_path(str(record["client_slug"]), slot.file_sha)


def _checked_form(path: Path, job: str) -> MeasuresForm:
    try:
        form = read_measures_form(path)
    except (OSError, ValueError, OfficeError) as exc:
        raise EmaError(
            "measures_form_invalid", "Formularul „Măsuri propuse” nu are coloanele aşteptate.", job
        ) from exc
    if form.header is None:
        raise EmaError(
            "measures_form_invalid", "Formularul „Măsuri propuse” nu are coloanele aşteptate.", job
        )
    return form


def validate_measures_form(ws: Workspace, job: str) -> None:
    _checked_form(_form_path(ws, job), job)


def _measure(
    ctx: StageContext, sha: str, number: int, row: MeasureRow, year: int
) -> PlannedMeasure:
    ws, job = ctx.ws, ctx.job
    prefix = f"audit_measure.{number}."
    source_fields = supplied_row(ws, job, sha, prefix, row)
    amount = float(source_fields["saving_amount"].value)
    unit = str(row.unit.value)
    carrier = row.carrier_value
    if unit == "tep":
        saving = supplied(
            ws,
            job,
            sha,
            FieldSpec(
                key=prefix + "saving_tep",
                label=field_label(prefix + "saving_tep"),
                value_type="number",
                unit="tep",
                chapter="ch6",
            ),
            row.saving_amount,
        )
    else:
        tep = measure_tep(amount, unit, carrier, year, FACTORS_2026)
        saving = calculated(
            ws, job, prefix + "saving_tep", replace(tep, inputs=(prefix + "saving_amount",))
        )
    co2 = measure_co2(amount, unit, carrier, year, FACTORS_2026)
    emissions = calculated(
        ws, job, prefix + "co2_t", replace(co2, inputs=(prefix + "saving_amount",))
    )
    investment = source_fields["investment_thousand_lei"].value
    cost = source_fields["cost_saving_thousand_lei"].value
    payback = payback_years(
        float(investment) if investment is not None else None,
        float(cost) if cost is not None else None,
    )
    trb = calculated(
        ws,
        job,
        prefix + "payback_years",
        replace(
            payback,
            inputs=(prefix + "investment_thousand_lei", prefix + "cost_saving_thousand_lei"),
        ),
    )
    narrative = absent(
        ws,
        job,
        FieldSpec(
            key=f"narrative.ch6.measure.{number}",
            label=f"Descrierea măsurii – {row.title.value}",
            value_type="text",
            chapter="ch6",
        ),
    )
    for field in (*source_fields.values(), saving, emissions, trb, narrative):
        ctx.record_read("fields.key", f"{job}:{field.key}", field.revision)
    return PlannedMeasure(
        title=str(row.title.value),
        effect=str(row.effect.value) if row.effect else None,
        saving_tep=float(saving.value) if saving.value is not None else None,
        co2_t=float(emissions.value) if emissions.value is not None else None,
        investment_thousand_lei=float(investment) if investment is not None else None,
        payback_years=float(trb.value) if trb.value is not None else None,
        cost_note=str(row.cost_note.value) if row.cost_note else None,
        narrative=str(narrative.value) if narrative.value is not None else None,
    )


def compose_measures(ctx: StageContext) -> StageOutcome:
    record = get_job(ctx.ws, ctx.job)
    slot = ctx.read_slot("measures")
    path = ctx.ws.file_path(str(record["client_slug"]), slot.file_sha)
    form = _checked_form(path, ctx.job)
    year = int(str(record["year"])) - 1
    ctx.record_input(factors=FACTORS_2026.version)
    count = supplied(
        ctx.ws,
        ctx.job,
        slot.file_sha,
        FieldSpec(
            key="audit_measure.count",
            label=field_label("audit_measure.count"),
            value_type="number",
            chapter="ch6",
        ),
        form.header,
        len(form.rows),
    )
    planned = tuple(
        _measure(ctx, slot.file_sha, index, row, year) for index, row in enumerate(form.rows, 1)
    )
    composition_facts = {field.key: field for field in fields(ctx.ws, ctx.job)}
    composition_facts[count.key] = count
    ctx.record_read("fields.key", f"{ctx.job}:{count.key}", count.revision)
    company = composition_facts.get("audit.company_name")
    ctx.record_read(
        "fields.key", f"{ctx.job}:audit.company_name", company.revision if company else 0
    )
    closing = absent(
        ctx.ws,
        ctx.job,
        FieldSpec(
            key="narrative.ch6.sinteza",
            label="Încheierea sintezei măsurilor",
            value_type="text",
            chapter="ch6",
        ),
    )
    composition_facts[closing.key] = closing
    ctx.record_read("fields.key", f"{ctx.job}:narrative.ch6.sinteza", closing.revision)
    plan = ChapterSixPlan(
        company_name=str(company.value) if company and company.value is not None else None,
        measures=planned,
        closing=str(closing.value)
        if closing.value is not None and closing.review != "rejected"
        else None,
    )
    folder = ctx.artifact_dir() / "sections"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ch6.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    record_material(ctx.ws, ctx.job, MaterialKind.MEASURES, True, "sha256:" + slot.file_sha)
    recompute_ready(ctx.ws, ctx.job)
    refresh_staleness(ctx.ws, ctx.job)
    keys = tuple(
        f"fact:{field.key}"
        for field in composition_facts.values()
        if field.key.startswith(("audit_measure.", "narrative.ch6."))
        or field.key == "audit.company_name"
    )
    queue_sections(
        ctx, ("ch6.specifice", "ch6.measure", "ch6.sinteza"), "ema", keys, facts=composition_facts
    )
    return StageOutcome(item_failures=[issue.detail for issue in form.issues])


def run_measures(ws: Workspace, job: str) -> MeasuresResult:
    validate_measures_form(ws, job)
    run = run_stage(ws, job, "measures", compose_measures)
    for _ in subscribe(ws, job):
        pass
    recorded = next(item for item in status(ws, job).runs if item["id"] == run)
    if recorded["state"] != "ready":
        raise EmaError("measures_failed", "Prelucrarea măsurilor a eşuat.", str(recorded["error"]))
    with ws.connect() as db:
        path = ws.artifact_dir(db, job, "measures", run) / "sections" / "ch6.json"
    plan = ChapterSixPlan.model_validate_json(path.read_text(encoding="utf-8"))
    return MeasuresResult(
        job,
        run,
        len(plan.measures),
        sum(item.payback_years is None for item in plan.measures),
        FACTORS_2026.version,
        sum(item.narrative is None for item in plan.measures),
        path,
    )
