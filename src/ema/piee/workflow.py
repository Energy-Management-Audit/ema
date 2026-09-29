"""PIEE import and generation shared by the command line and the HTTP API."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import (
    StageContext,
    StageOutcome,
    create_job,
    get_job,
    latest_ready_run,
    run_stage,
    status,
    subscribe,
)
from ema.core.jobs.reads import run_current
from ema.core.review.models import Cell, Field
from ema.core.workspace import Workspace
from ema.energy_data.prelucrare import import_prelucrare
from ema.energy_data.prelucrare_writer import write_prelucrare
from ema.piee.base import build_local_base
from ema.piee.compose import compose_draft, load_approved_base
from ema.piee.dataset import PieeData, load
from ema.piee.intake import import_piee_into_job
from ema.piee.review_overlay import apply_review
from ema.piee.views import prelucrare_state


def base_directory(ws: Workspace) -> Path:
    settings = load_settings(ws)
    base = settings.piee_base_document
    if base is None or not base.is_file():
        raise EmaError("piee_base_missing", "Documentul de bază PIEE lipseşte.", str(base))
    base_sha = hashlib.sha256(base.read_bytes()).hexdigest()
    directory = settings.piee_base_directory or ws.root / "bases" / "piee" / base_sha[:16]
    if not (directory / "base-map.json").is_file():
        build_local_base(base, directory)
    if not (directory / "approval.json").is_file():
        raise EmaError(
            "piee_base_review_required",
            "Harta documentului de bază necesită verificare în Word.",
            str(directory / "piee-preview.docx"),
        )
    mapping = load_approved_base(directory)
    if mapping.base_sha != base_sha:
        raise EmaError("piee_base_changed", "Documentul de bază PIEE a fost schimbat.", str(base))
    return directory


@dataclass(frozen=True)
class GenerateRequest:
    client: str
    year: int
    anexa: Path
    necesar: Path | None = None
    prelucrare: Path | None = None
    previous_piee: Path | None = None


def start_generate(
    ws: Workspace, request: GenerateRequest, *, generated_on: date | None = None
) -> tuple[str, str]:
    """Read the documents, wait for the import, then render one draft (the CLI one-call path)."""
    load(
        request.year,
        request.anexa,
        request.necesar,
        request.prelucrare,
        request.previous_piee,
    )
    job = create_job(ws, "piee", request.client, request.year + 1)
    for slot, path in (
        ("anexa", request.anexa),
        ("questionnaire", request.necesar),
        ("prelucrare", request.prelucrare),
        ("previous_piee", request.previous_piee),
    ):
        if path is not None:
            ws.set_slot(job, slot, ws.add_file(request.client, path))
    run = start_import_for_job(ws, job)
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    if record["state"] != "ready":
        raise EmaError(
            "piee_import_failed", "Documentele nu s-au putut citi.", str(record["error"])
        )
    return job, start_generate_for_job(ws, job, generated_on=generated_on)


@dataclass(frozen=True)
class GeneratedDraft:
    job: str
    run: str
    draft: Path
    workbook: Path


def generate_draft(ws: Workspace, request: GenerateRequest) -> GeneratedDraft:
    """Create the job, wait for its draft run, and return both published drafts."""
    job, run = start_generate(ws, request)
    for _ in subscribe(ws, job):
        pass
    record = next(item for item in status(ws, job).runs if item["id"] == run)
    if record["state"] != "ready":
        raise EmaError("piee_generation_failed", "Generarea PIEE a eşuat.", str(record["error"]))
    with ws.connect() as db:
        rows = db.execute(
            "SELECT relative_path FROM outputs WHERE job_id=? AND run_id=? AND kind='draft'",
            (job, run),
        ).fetchall()
    paths = {ws.path(str(row["relative_path"])) for row in rows}
    draft = next((path for path in paths if path.suffix == ".docx"), None)
    workbook = next((path for path in paths if path.suffix == ".xlsx"), None)
    if draft is None or workbook is None:
        raise EmaError("piee_output_missing", "Ciorna PIEE lipseşte.", run)
    return GeneratedDraft(job, run, draft, workbook)


@dataclass(frozen=True)
class _Sources:
    data_year: int
    shas: dict[str, str]
    paths: dict[str, Path]

    def load(self) -> PieeData:
        return load(
            self.data_year,
            self.paths["anexa"],
            self.paths.get("questionnaire"),
            self.paths.get("prelucrare"),
            self.paths.get("previous_piee"),
        )


def _sources(ws: Workspace, job: str) -> _Sources:
    record = get_job(ws, job)
    if record["type"] != "piee":
        raise EmaError("wrong_job_type", "Lucrarea nu este PIEE.", "")
    job_year = record["year"]
    if not isinstance(job_year, int) or job_year < 2:
        raise EmaError("invalid_year", "Anul lucrării este invalid.", "")
    client = str(record["client_slug"])
    with ws.connect() as db:
        slots = db.execute(
            "SELECT s.name,v.file_sha FROM slots s JOIN slot_versions v ON "
            "v.job_id=s.job_id AND v.slot=s.name AND v.version=s.active_version "
            "WHERE s.job_id=?",
            (job,),
        ).fetchall()
    shas = {str(row["name"]): str(row["file_sha"]) for row in slots}
    if "anexa" not in shas:
        raise EmaError("not_ready", "Anexa lipseşte.", "")
    paths = {name: ws.file_path(client, sha) for name, sha in shas.items()}
    return _Sources(job_year - 1, shas, paths)


def _check_reads(ctx: StageContext, expected: dict[str, str]) -> None:
    read = {slot.slot: slot.file_sha for slot in ctx.read_slots("")}
    if read != expected:
        raise EmaError("stale_revision", "Fişierele lucrării s-au schimbat.", "")


def start_import_for_job(ws: Workspace, job: str, *, on_revision: int | None = None) -> str:
    """Read every source slot into review fields; generation composes from these fields."""
    sources = _sources(ws, job)
    sources.load()

    def stage(ctx: StageContext) -> StageOutcome:
        ctx.progress(0, 1, "Citire documente PIEE")
        _check_reads(ctx, sources.shas)
        import_piee_into_job(
            ws,
            job,
            sources.data_year,
            sources.paths["anexa"],
            sources.paths.get("questionnaire"),
            sources.paths.get("prelucrare"),
            previous_piee=sources.paths.get("previous_piee"),
        )
        ctx.progress(1, 1, "Date citite")
        return StageOutcome()

    return run_stage(ws, job, "piee_import", stage, on_revision=on_revision)


def current_import(ws: Workspace, job: str) -> str | None:
    """The latest import whose documents are still the job's active slots."""
    run = latest_ready_run(ws, job, "piee_import")
    if run is None:
        return None
    with ws.connect() as db:
        return run if run_current(db, run) else None


def _reviewed(ws: Workspace, ctx: StageContext, data: PieeData) -> PieeData:
    with ws.connect() as db:
        db.execute("BEGIN")
        rows = db.execute(
            "SELECT id,revision,data FROM fields WHERE job_id=? ORDER BY key", (ctx.job,)
        ).fetchall()
        evidence = db.execute("SELECT id,data FROM evidence WHERE job_id=?", (ctx.job,)).fetchall()
    fields: list[Field] = []
    for row in rows:
        ctx.record_read("fields", str(row["id"]), int(row["revision"]))
        fields.append(Field.model_validate_json(row["data"]))
    cells: dict[str, Cell] = {}
    for row in evidence:
        # Older evidence rows predate `provenance`, so only the locator is validated.
        locator = cast("dict[str, object]", json.loads(row["data"])).get("locator")
        if isinstance(locator, dict) and cast("dict[str, object]", locator).get("kind") == "cell":
            cells[str(row["id"])] = Cell.model_validate(locator)
    return apply_review(data, fields, cells)


def start_generate_for_job(
    ws: Workspace,
    job: str,
    *,
    generated_on: date | None = None,
    on_revision: int | None = None,
) -> str:
    """Compose a draft from the current import's fields; it never reads the documents anew."""
    sources = _sources(ws, job)
    source_shas = sources.shas
    imported = current_import(ws, job)
    if imported is None:
        raise EmaError("import_required", "Documentele trebuie citite din nou.", "")
    with ws.connect() as db:
        import_shas = {
            str(row["file_sha"])
            for row in db.execute("SELECT file_sha FROM run_inputs WHERE run_id=?", (imported,))
        }
    if import_shas != set(source_shas.values()):
        raise EmaError("import_required", "Documentele trebuie citite din nou.", "")
    base_data = sources.load()
    base = base_directory(ws)
    today = generated_on or date.today()

    def stage(ctx: StageContext) -> StageOutcome:
        ctx.progress(0, 2, "Pregătire date PIEE")
        _check_reads(ctx, source_shas)
        data = _reviewed(ws, ctx, base_data)
        ctx.record_input(template=load_approved_base(base).base_sha, factors=data.factors.version)
        temporary = ctx.artifact_dir() / "PIEE-draft.docx"
        result = compose_draft(data, base, temporary, today)
        ctx.progress(1, 2, "Ciornă generată")
        status_path = ctx.artifact_dir() / "PIEE-checks.json"
        status_path.write_text(
            json.dumps(
                {
                    "untouched": result.untouched,
                    "package_issues": result.package_issues,
                    "leftover_parts": result.leftover_parts,
                    "final_ready": result.final_ready,
                    "production_conversion": (
                        {
                            "source_unit": data.production_conversion.source_unit,
                            "presentation_unit": data.production_conversion.presentation_unit,
                            "multiplier": data.production_conversion.multiplier,
                            "source": data.production_conversion.source,
                        }
                        if data.production_conversion is not None
                        else None
                    ),
                    "pie_value_representation": {
                        "value": data.pie_representation,
                        "source": data.pie_representation_source,
                    },
                    "separate_pv_figures": {
                        "value": data.separate_pv_figures,
                        "source": "previous_piee" if "previous_piee" in source_shas else "base",
                    },
                }
            ),
            encoding="utf-8",
        )
        workbook = ctx.artifact_dir() / "Prelucrare-date.xlsx"
        write_prelucrare(
            data.dataset,
            data.dataset.years,
            workbook,
            data.factors,
            firm_name=load_settings(ws).firm_name,
        )
        ctx.save_output(workbook, "Prelucrare-date.xlsx")
        ctx.save_output(temporary, "PIEE-draft.docx")
        ctx.progress(2, 2, "Prelucrare date generată")
        return StageOutcome(warnings=[f"untouched anchors: {len(result.untouched)}"])

    return run_stage(ws, job, "piee_generate", stage, on_revision=on_revision)


def set_prelucrare(ws: Workspace, job: str, file_id: str, role: str = "input") -> dict[str, object]:
    if role != "input":
        raise EmaError("file_type", "Tipul fişierului este invalid.", "")
    record = get_job(ws, job)
    if record["type"] != "piee":
        raise EmaError("wrong_job_type", "Lucrarea nu este PIEE.", "")
    if record["state"] == "running":
        raise EmaError("job_running", "Lucrarea rulează deja.", "")
    path = ws.file_path(str(record["client_slug"]), file_id)
    if path.suffix.lower() not in {".xls", ".xlsx"}:
        raise EmaError("file_type", "Tipul fişierului este invalid.", "")
    import_prelucrare(path)
    ws.set_slot(job, "prelucrare", file_id)
    return prelucrare_state(ws, job)
