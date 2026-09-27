"""Read visit photos by replay and leave every extracted value for human confirmation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ema.audit.prompts import (
    METER_PROMPT,
    METER_PROMPT_VERSION,
    THERMAL_PROMPT,
    THERMAL_PROMPT_VERSION,
)
from ema.audit.readings_schema import UNITS, DisplayValue, MeterReadout, ThermalReadout
from ema.audit.visit import VisitPanel, VisitPhoto, visit_view, visit_view_from_slots
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, get_job, run_stage, status, subscribe
from ema.core.llm.agent import AgentContext
from ema.core.llm.models import selected_model
from ema.core.llm.replay import ReplayProvider
from ema.core.llm.structured import complete_json
from ema.core.llm.types import ImageInput, Provider
from ema.core.logging import write_event
from ema.core.office.sniff import FileKind, sniff
from ema.core.review import fields, mark_absent, propose
from ema.core.review.models import Evidence, Field, FieldSpec, Photo
from ema.core.workspace import Workspace

REPLAY_MODEL = "gemini-3.6-flash"


@dataclass(frozen=True)
class ReadingsResult:
    job: str
    run: str
    photos_read: int
    photos_failed: int
    readings: int
    needs_confirmation: int


def _number(value: str) -> Decimal:
    try:
        number = Decimal(value.replace(" ", "").replace(",", "."))
        if not number.is_finite():
            raise InvalidOperation
        return number
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("displayed number is invalid") from exc


def _proof(ctx: StageContext, photo: VisitPhoto, key: str, value: str, region: Photo) -> Evidence:
    evidence_id = hashlib.sha256(f"vision:{photo.sha}:{key}:{value}".encode()).hexdigest()
    with ctx.ws.connect() as db:
        row = db.execute("SELECT data FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if row is not None:
        return Evidence.model_validate_json(row["data"])
    return Evidence(
        id=evidence_id,
        provenance="document",
        file_sha=photo.sha,
        locator=region,
        method="vision",
        retrieved_at=datetime.now(UTC),
        highlight="page",
    )


def _image(ws: Workspace, client: str, photo: VisitPhoto) -> ImageInput:
    path = ws.file_path(client, photo.sha)
    detected = sniff(path)
    if detected.kind != FileKind.IMAGE or detected.media_type is None:
        raise ValueError("photo is not a supported image")
    return ImageInput(photo.sha, detected.media_type, path.read_bytes())


def _propose(
    ctx: StageContext,
    photo: VisitPhoto,
    spec: FieldSpec,
    value: str | Decimal,
    region: tuple[float, float, float, float] | None = None,
    *,
    preserve_reviewed: bool = False,
) -> None:
    locator = Photo(region=region)
    proof = _proof(ctx, photo, spec.key, str(value), locator)
    propose(
        ctx.ws,
        ctx.job,
        spec,
        value,
        [proof],
        state="extracted",
        needs_confirmation=True,
        preserve_reviewed=preserve_reviewed,
    )


def _meter(
    ctx: StageContext,
    provider: Provider,
    model_id: str,
    client: str,
    panel: VisitPanel,
    photo: VisitPhoto,
) -> None:
    context = AgentContext(
        ctx.ws, ctx.job, "readings", provider, model_id, METER_PROMPT_VERSION, synthetic=False
    )
    readout = complete_json(
        context,
        MeterReadout,
        METER_PROMPT,
        f"Panel: {panel.label}\nPhoto: {photo.name}",
        images=(_image(ctx.ws, client, photo),),
    )
    if not readout.readable or readout.display is None:
        raise ValueError(readout.unreadable_reason or "display unreadable")
    parsed: list[tuple[DisplayValue, Decimal]] = []
    for entry in readout.values:
        if entry.unit not in UNITS[entry.quantity]:
            raise ValueError("unit outside meter vocabulary")
        Photo(region=entry.region)
        parsed.append((entry, _number(entry.value)))
    prefix = f"meter.{panel.id}.{photo.sha[:8]}"
    _propose(
        ctx,
        photo,
        FieldSpec(
            key=f"{prefix}.display",
            label=photo.name,
            value_type="enum",
            chapter="ch5.electric_fisa",
        ),
        readout.display,
    )
    if readout.device:
        _propose(
            ctx,
            photo,
            FieldSpec(
                key=f"meter.{panel.id}.device",
                label=f"Aparatul de măsură – {panel.label}",
                value_type="text",
                chapter="ch5.electric_fisa",
            ),
            readout.device,
            preserve_reviewed=True,
        )
    for entry, value in parsed:
        _propose(
            ctx,
            photo,
            FieldSpec(
                key=f"{prefix}.{entry.quantity}.{entry.phase}",
                label=f"{entry.quantity} {entry.phase}",
                value_type="number",
                unit=entry.unit,
                chapter="ch5.electric_fisa",
            ),
            value,
            entry.region,
        )


def _thermal(
    ctx: StageContext, provider: Provider, model_id: str, client: str, photo: VisitPhoto
) -> None:
    context = AgentContext(
        ctx.ws, ctx.job, "readings", provider, model_id, THERMAL_PROMPT_VERSION, synthetic=False
    )
    readout = complete_json(
        context,
        ThermalReadout,
        THERMAL_PROMPT,
        f"Photo: {photo.name}",
        images=(_image(ctx.ws, client, photo),),
    )
    if not readout.readable or not readout.component:
        raise ValueError(readout.unreadable_reason or "thermal overlay unreadable")
    parsed = {
        name: _number(value)
        for name in ("spot", "max", "min")
        if (value := getattr(readout, name)) is not None
    }
    prefix = f"thermal.{photo.sha[:8]}"
    _propose(
        ctx,
        photo,
        FieldSpec(
            key=f"{prefix}.component",
            label="Componentă",
            value_type="text",
            chapter="ch5.termic_fisa",
        ),
        readout.component,
    )
    for name, value in parsed.items():
        _propose(
            ctx,
            photo,
            FieldSpec(
                key=f"{prefix}.{name}",
                label=name,
                value_type="number",
                unit="°C",
                chapter="ch5.termic_fisa",
            ),
            value,
        )


def _failed(ctx: StageContext, photo: VisitPhoto, key: str, reason: str) -> None:
    with ctx.ws.connect() as db:
        row = db.execute(
            "SELECT data FROM fields WHERE job_id=? AND key=?", (ctx.job, key)
        ).fetchone()
        with ctx.ws.job_log(db, ctx.job) as handle:
            write_event(handle, "photo_unreadable", run=ctx.run_id, slot=photo.slot, detail=reason)
    failure = "photo_unreadable"
    if row is not None:
        old = Field.model_validate_json(row["data"])
        if old.presence == "failed" and old.failure == failure:
            return
    mark_absent(ctx.ws, ctx.job, key, "failed", failure=failure)


def read_photos(ctx: StageContext, *, provider: Provider, model_id: str) -> StageOutcome:  # noqa: C901
    model = selected_model("gemini" if provider.name == "replay" else provider.name, model_id)
    if not model.vision:
        raise EmaError("model_no_vision", "Modelul ales nu citeşte imagini.", model_id)
    client = str(get_job(ctx.ws, ctx.job)["client_slug"])
    view = visit_view_from_slots(ctx.read_slots("visit"))
    failures: list[str] = []
    ctx.record_input(prompt=f"{METER_PROMPT_VERSION},{THERMAL_PROMPT_VERSION}", model=model_id)
    for panel in view.panels:
        for photo in panel.photos:
            try:
                _meter(ctx, provider, model_id, client, panel, photo)
            except EmaError as exc:
                if exc.code != "ai_schema":
                    raise
                _failed(ctx, photo, f"meter.{panel.id}.{photo.sha[:8]}.display", exc.code)
                failures.append(f"photo_unreadable:{photo.slot}")
            except (ValueError, OSError) as exc:
                _failed(ctx, photo, f"meter.{panel.id}.{photo.sha[:8]}.display", str(exc))
                failures.append(f"photo_unreadable:{photo.slot}")
    for photo in view.thermal:
        try:
            _thermal(ctx, provider, model_id, client, photo)
        except EmaError as exc:
            if exc.code != "ai_schema":
                raise
            _failed(ctx, photo, f"thermal.{photo.sha[:8]}.component", exc.code)
            failures.append(f"photo_unreadable:{photo.slot}")
        except (ValueError, OSError) as exc:
            _failed(ctx, photo, f"thermal.{photo.sha[:8]}.component", str(exc))
            failures.append(f"photo_unreadable:{photo.slot}")
    return StageOutcome(item_failures=failures)


def run_readings(ws: Workspace, job: str, *, recording: Path | None) -> ReadingsResult:
    if get_job(ws, job)["type"] != "audit":
        raise EmaError("wrong_job_type", "Lucrarea nu este un audit.", job)
    if recording is None:
        raise EmaError("ai_client_disabled", "Citirea fotografiilor aşteaptă aprobarea.", "")
    try:
        provider = ReplayProvider(recording)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise EmaError("replay_invalid", "Înregistrarea AI este invalidă.", recording.name) from exc
    failure: list[Exception] = []

    def stage(ctx: StageContext) -> StageOutcome:
        try:
            return read_photos(ctx, provider=provider, model_id=REPLAY_MODEL)
        except Exception as exc:
            failure.append(exc)
            raise

    run = run_stage(ws, job, "readings", stage)
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    if record["state"] != "ready":
        if failure and isinstance(failure[0], EmaError):
            raise failure[0]
        raise EmaError("readings_failed", "Citirea fotografiilor a eşuat.", str(record["error"]))
    failed = len(json.loads(str(record["outcome"]))["item_failures"])
    view = visit_view(ws, job)
    all_fields = fields(ws, job)
    reading_fields = [
        field
        for field in all_fields
        if field.key.startswith(("meter.", "thermal."))
        and field.key.split(".")[-1] not in {"display", "device", "component"}
    ]
    total = sum(len(panel.photos) for panel in view.panels) + len(view.thermal)
    return ReadingsResult(
        job,
        run,
        total - failed,
        failed,
        len(reading_fields),
        sum(field.needs_confirmation for field in all_fields),
    )
