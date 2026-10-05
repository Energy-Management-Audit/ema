"""Deterministic chapter-five plan from current photos and confirmed readings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel
from pydantic import Field as PydanticField

from ema.audit.catalogue import CATALOGUE
from ema.audit.chapter_five_notes import NOTE_PREFIX, write_notes
from ema.audit.measurement_rules import assess
from ema.audit.publication import queue_sections, record_field_prefixes
from ema.audit.sections import Status, get_status, recompute_ready
from ema.audit.visit import VisitPanel, VisitPhoto, VisitView, visit_view, visit_view_from_slots
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, get_job, run_stage, status, subscribe
from ema.core.resources import resource_path
from ema.core.review import fields, mark_absent
from ema.core.review.models import Field, FieldSpec
from ema.core.workspace import Workspace


class PlannedReading(BaseModel):
    key: str
    label: str
    value: str | None
    unit: str | None


class PlannedPhoto(BaseModel):
    slot: str
    sha: str
    name: str
    caption: str
    display: str | None
    readings: list[PlannedReading]
    norm: str | None
    narrative_key: str | None


class PlannedPanel(BaseModel):
    id: str
    label: str
    device: str | None
    photos: list[PlannedPhoto]


class PlannedThermal(BaseModel):
    slot: str
    sha: str
    name: str
    component: str | None


class ChapterFivePlan(BaseModel):
    panels: list[PlannedPanel]
    thermal: list[PlannedThermal]
    visit_date: str | None
    client: str | None
    missing_narratives: list[str]
    narratives: dict[str, str | None] = PydanticField(default_factory=dict)


@dataclass(frozen=True)
class MeasurementsResult:
    job: str
    run: str
    figures: int
    confirmed: int
    pending: int
    missing_narratives: int
    missing_sections: tuple[str, ...]
    plan_path: Path


def _confirmed(field: Field | None) -> bool:
    return (
        field is not None
        and field.value is not None
        and field.review in {"accepted", "corrected"}
        and not field.needs_confirmation
    )


def _value(field: Field | None) -> str | None:
    return str(field.value) if field is not None and _confirmed(field) else None


def _narrative(key: str, field: Field) -> str | None:
    # An equipment note renders until it is rejected; the other texts once a person confirms them.
    if key.startswith(NOTE_PREFIX):
        return str(field.value) if field.value is not None and field.review != "rejected" else None
    return _value(field)


def _phrases() -> dict[str, str]:
    with resource_path("audit", "measurement_phrases.json").open(encoding="utf-8") as handle:
        entries = json.load(handle)
    return {str(entry["id"]): str(entry["template"]) for entry in entries}


def _photo_plan(
    panel: VisitPanel, photo: VisitPhoto, facts: dict[str, Field], phrases: dict[str, str]
) -> PlannedPhoto:
    prefix = f"meter.{panel.id}.{photo.sha[:8]}"
    display_field = facts.get(f"{prefix}.display")
    display = _value(display_field)
    caption = phrases.get(display or "overview", "Valorile afișate")
    reading_fields = [
        field
        for key, field in sorted(facts.items())
        if key.startswith(prefix + ".") and key != prefix + ".display"
    ]
    readings = [
        PlannedReading(
            key=field.key,
            label=field.label,
            value=str(field.value) if _confirmed(field) else None,
            unit=field.unit,
        )
        for field in reading_fields
    ]
    outcomes = assess(reading_fields)
    needs_narrative = any(item.status in {"fail", "unsupported"} for item in outcomes)
    norm = ", ".join(item.rule for item in outcomes if item.status == "pass") or None
    return PlannedPhoto(
        slot=photo.slot,
        sha=photo.sha,
        name=photo.name,
        caption=caption,
        display=display,
        readings=readings,
        norm=norm,
        narrative_key=f"narrative.ch5.{panel.id}.{photo.sha[:8]}" if needs_narrative else None,
    )


def _plan(view: VisitView, facts: dict[str, Field]) -> ChapterFivePlan:
    phrases = _phrases()
    panels = [
        PlannedPanel(
            id=panel.id,
            label=panel.label,
            device=_value(facts.get(f"meter.{panel.id}.device")),
            photos=[_photo_plan(panel, photo, facts, phrases) for photo in panel.photos],
        )
        for panel in view.panels
    ]
    thermal = [
        PlannedThermal(
            slot=photo.slot,
            sha=photo.sha,
            name=photo.name,
            component=_value(facts.get(f"thermal.{photo.sha[:8]}.component")),
        )
        for photo in view.thermal
    ]
    date = facts.get("visit.date")
    client = facts.get("audit.company_name")
    narrative_keys = [
        *(
            photo.narrative_key
            for panel in panels
            for photo in panel.photos
            if photo.narrative_key is not None
        ),
        *(
            ["narrative.ch5.electric_rezultate", "narrative.ch5.electric_concluzii"]
            if any(photo.narrative_key for panel in panels for photo in panel.photos)
            else []
        ),
        *(["narrative.ch5.termic_rezultate"] if thermal else []),
    ]
    missing = [key for key in narrative_keys if not _confirmed(facts.get(key))]
    return ChapterFivePlan(
        panels=panels,
        thermal=thermal,
        visit_date=_value(date),
        client=_value(client),
        missing_narratives=missing,
        narratives={
            key: _narrative(key, field)
            for key, field in facts.items()
            if key.startswith("narrative.ch5.")
        },
    )


def chapter_five_plan(ws: Workspace, job: str) -> ChapterFivePlan:
    return _plan(visit_view(ws, job), {field.key: field for field in fields(ws, job)})


def compose_measurements(ctx: StageContext, recording: Path | None = None) -> StageOutcome:
    ws, job = ctx.ws, ctx.job
    slots = ctx.read_slots("visit")
    current_fields = fields(ws, job)
    for field in current_fields:
        if (
            field.key.startswith(("meter.", "thermal.", "visit.", "narrative.ch5."))
            or field.key == "audit.company_name"
        ):
            ctx.record_read("fields", field.id, field.revision)
    view = visit_view_from_slots(slots)
    by_key = {field.key: field for field in current_fields}
    plan = _plan(view, by_key)
    notes, warnings = write_notes(ctx, plan, by_key, recording)
    if notes:
        by_key.update({field.key: field for field in notes})
        plan = _plan(view, by_key)
    existing = set(by_key)
    labels = {
        photo.narrative_key: f"Interpretarea – {panel.label}, {photo.caption}"
        for panel in plan.panels
        for photo in panel.photos
        if photo.narrative_key
    }
    labels.update(
        {
            "narrative.ch5.electric_rezultate": "Rezultatele măsurătorilor electroenergetice",
            "narrative.ch5.electric_concluzii": "Concluziile măsurătorilor electroenergetice",
            "narrative.ch5.termic_rezultate": "Rezultatele măsurătorilor termoenergetice",
        }
    )
    for key in plan.missing_narratives:
        if key not in existing:
            by_key[key] = mark_absent(
                ws,
                job,
                FieldSpec(key=key, label=labels[key], value_type="text", chapter="ch5"),
                "not_found",
            )
    directory = ctx.artifact_dir() / "sections"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ch5.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    recompute_ready(ws, job)
    used_keys = {
        key
        for key in existing
        if key.startswith(("meter.", "thermal.", "visit.", "narrative.ch5."))
    }
    used = tuple(
        f"fact:{key}"
        for key in sorted(used_keys | set(plan.missing_narratives) | {"audit.company_name"})
    )
    record_field_prefixes(ctx, by_key, ("meter.", "thermal.", "visit.", "narrative.ch5."))
    queue_sections(
        ctx,
        (section.id for section in CATALOGUE if section.id.startswith("ch5")),
        "ema",
        used,
        facts=by_key,
    )
    return StageOutcome(warnings=warnings)


def start_measurements(
    ws: Workspace, job: str, *, on_revision: int | None = None, recording: Path | None = None
) -> str:
    """Compose chapter five; its equipment notes replay `recording` when one is given."""
    if get_job(ws, job)["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    return run_stage(
        ws,
        job,
        "measurements",
        lambda ctx: compose_measurements(ctx, recording),
        on_revision=on_revision,
    )


def run_measurements(
    ws: Workspace, job: str, *, recording: Path | None = None
) -> MeasurementsResult:
    run = start_measurements(ws, job, recording=recording)
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    if record["state"] != "ready":
        raise EmaError(
            "measurements_failed", "Compunerea măsurătorilor a eşuat.", str(record["error"])
        )
    plan = chapter_five_plan(ws, job)
    confirmed = sum(
        reading.value is not None
        for panel in plan.panels
        for photo in panel.photos
        for reading in photo.readings
    )
    pending = sum(
        reading.value is None
        for panel in plan.panels
        for photo in panel.photos
        for reading in photo.readings
    )
    missing_sections = tuple(
        section.id
        for section in CATALOGUE
        if section.id.startswith("ch5") and get_status(ws, job, section.id).status == Status.MISSING
    )
    with ws.connect() as db:
        path = ws.artifact_dir(db, job, "measurements", run) / "sections" / "ch5.json"
    return MeasurementsResult(
        job,
        run,
        sum(len(panel.photos) for panel in plan.panels) + len(plan.thermal),
        confirmed,
        pending,
        len(plan.missing_narratives),
        missing_sections,
        path,
    )
