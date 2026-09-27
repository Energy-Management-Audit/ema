"""Register audit visit photos without requiring dossier intake."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

from pydantic import BaseModel

from ema.audit.catalogue import MaterialKind
from ema.audit.sections import recompute_ready, record_material
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, get_job, run_stage, status, subscribe
from ema.core.office.sniff import FileKind, sniff
from ema.core.review import mark_absent
from ema.core.review.models import FieldSpec
from ema.core.workspace import SlotVersion, Workspace
from ema.core.workspace.conversion import active_version


class VisitPhoto(BaseModel):
    sha: str
    slot: str
    name: str


class VisitPanel(BaseModel):
    id: str
    label: str
    photos: list[VisitPhoto]


class VisitView(BaseModel):
    panels: list[VisitPanel]
    thermal: list[VisitPhoto]


@dataclass(frozen=True)
class VisitResult:
    job: str
    run: str
    panels: int
    meter_photos: int
    thermal_images: int
    failures: tuple[str, ...]


def slug(label: str) -> str:
    folded = unicodedata.normalize("NFKD", label)
    ascii_text = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def _natural(value: str) -> list[int | str]:
    return [
        int(part) if part.isdecimal() else part.casefold() for part in re.split(r"(\d+)", value)
    ]


def _kinds(slots: list[SlotVersion]) -> tuple[list[SlotVersion], list[SlotVersion]]:
    meter: list[SlotVersion] = []
    thermal: list[SlotVersion] = []
    for version in slots:
        parts = version.slot.split("/")
        if len(parts) == 4 and parts[:2] == ["visit", "meter"]:
            meter.append(version)
        elif len(parts) == 3 and parts[:2] == ["visit", "thermal"]:
            thermal.append(version)
    return meter, thermal


def visit_view_from_slots(slots: list[SlotVersion]) -> VisitView:
    meter, thermal = _kinds(slots)
    grouped: dict[str, list[VisitPhoto]] = {}
    for version in meter:
        panel, name = version.slot.split("/")[2:]
        grouped.setdefault(panel, []).append(
            VisitPhoto(sha=version.file_sha, slot=version.slot, name=name)
        )
    panels = [
        VisitPanel(
            id=slug(label),
            label=label,
            photos=sorted(grouped[label], key=lambda photo: _natural(photo.name)),
        )
        for label in sorted(grouped, key=_natural)
    ]
    thermal_photos = [
        VisitPhoto(sha=version.file_sha, slot=version.slot, name=version.slot.split("/")[-1])
        for version in thermal
    ]
    return VisitView(panels=panels, thermal=sorted(thermal_photos, key=lambda p: _natural(p.name)))


def visit_view(ws: Workspace, job: str) -> VisitView:
    if get_job(ws, job)["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    slots = [
        version
        for name in ws.list_slots(job, "visit")
        if (version := active_version(ws, job, name)) is not None
    ]
    return visit_view_from_slots(slots)


def _source(slots: list[SlotVersion]) -> str:
    listing = "\n".join(
        f"{item.slot} {item.file_sha}" for item in sorted(slots, key=lambda item: item.slot)
    )
    return "sha256:" + hashlib.sha256(listing.encode()).hexdigest()


def register_visit(ctx: StageContext) -> StageOutcome:
    ws, job = ctx.ws, ctx.job
    record = get_job(ws, job)
    meter, thermal = _kinds(ctx.read_slots("visit"))
    if not meter and not thermal:
        raise EmaError("visit_missing", "Fotografiile din vizită lipsesc.", job)
    failures: list[str] = []
    for version in [*meter, *thermal]:
        path = ws.file_path(str(record["client_slug"]), version.file_sha)
        if sniff(path).kind != FileKind.IMAGE:
            failures.append(f"visit_not_image:{version.slot}")
    record_material(ws, job, MaterialKind.METER, bool(meter), _source(meter))
    record_material(ws, job, MaterialKind.THERMAL, bool(thermal), _source(thermal))
    view = visit_view_from_slots([*meter, *thermal])
    specs = [FieldSpec(key="visit.date", label="Data vizitei", value_type="date", chapter="ch5")]
    specs.extend(
        FieldSpec(
            key=f"meter.{panel.id}.device",
            label=f"Aparatul de măsură – {panel.label}",
            value_type="text",
            chapter="ch5.electric_fisa",
        )
        for panel in view.panels
    )
    for spec in specs:
        mark_absent(ws, job, spec, "not_found", only_if_missing=True)
    (ctx.artifact_dir() / "visit.json").write_text(view.model_dump_json(indent=2), "utf-8")
    recompute_ready(ws, job)
    return StageOutcome(item_failures=failures)


def start_visit(ws: Workspace, job: str, *, on_revision: int | None = None) -> str:
    if get_job(ws, job)["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    view = visit_view(ws, job)
    if not view.panels and not view.thermal:
        raise EmaError("visit_missing", "Fotografiile din vizită lipsesc.", job)
    return run_stage(ws, job, "visit", register_visit, on_revision=on_revision)


def run_visit(ws: Workspace, job: str) -> VisitResult:
    run = start_visit(ws, job)
    for _ in subscribe(ws, job):
        pass
    result = next(item for item in status(ws, job).runs if item["id"] == run)
    if result["state"] != "ready":
        raise EmaError("visit_failed", "Înregistrarea vizitei a eşuat.", str(result["error"]))
    outcome = json.loads(str(result["outcome"]))
    view = visit_view(ws, job)
    return VisitResult(
        job,
        run,
        len(view.panels),
        sum(len(panel.photos) for panel in view.panels),
        len(view.thermal),
        tuple(outcome["item_failures"]),
    )
