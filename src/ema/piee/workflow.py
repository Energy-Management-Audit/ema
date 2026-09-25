"""PIEE job generation shared by the command line and future HTTP adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import (
    StageContext,
    StageOutcome,
    create_job,
    get_job,
    latest_ready_run,
    run_stage,
)
from ema.core.workspace import Workspace
from ema.energy_data.prelucrare import import_prelucrare
from ema.energy_data.prelucrare_writer import write_prelucrare
from ema.piee.base import build_local_base
from ema.piee.compose import compose_draft, load_approved_base
from ema.piee.dataset import load
from ema.piee.intake import import_piee_into_job
from ema.piee.views import prelucrare_state


def base_directory(ws: Workspace) -> Path:
    settings = load_settings(ws)
    base = settings.piee_base_document
    if base is None or not base.is_file():
        raise EmaError("piee_base_missing", "Documentul de bază PIEE lipsește.", str(base))
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
    """Import review evidence, then render one draft from immutable slot copies."""
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
    return job, start_generate_for_job(ws, job, generated_on=generated_on)


def start_generate_for_job(
    ws: Workspace,
    job: str,
    *,
    generated_on: date | None = None,
    on_revision: int | None = None,
) -> str:
    """Generate from the active slots of a pre-existing year-N+1 PIEE job."""
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
    source_shas = {str(row["name"]): str(row["file_sha"]) for row in slots}
    sources = {name: ws.file_path(client, sha) for name, sha in source_shas.items()}
    if "anexa" not in sources:
        raise EmaError("not_ready", "Anexa lipsește.", "")
    data_year = job_year - 1
    previous = latest_ready_run(ws, job, "piee_generate")
    with ws.connect() as db:
        current_slots = {
            (str(row["name"]), int(row["revision"]))
            for row in db.execute(
                "SELECT name,revision FROM slots WHERE job_id=? AND active_version IS NOT NULL",
                (job,),
            )
        }
        previous_slots: set[tuple[str, int]] = (
            {
                (str(row["row_id"]).split(":", 1)[1], int(row["revision"]))
                for row in db.execute(
                    "SELECT row_id,revision FROM run_reads WHERE run_id=? AND table_name='slots'",
                    (previous,),
                )
            }
            if previous is not None
            else set()
        )
    needs_import = previous is None or current_slots != previous_slots
    data = load(
        data_year,
        sources["anexa"],
        sources.get("questionnaire"),
        sources.get("prelucrare"),
        sources.get("previous_piee"),
    )
    base = base_directory(ws)
    today = generated_on or date.today()

    def stage(ctx: StageContext) -> StageOutcome:
        ctx.progress(0, 2, "Pregătire date PIEE")
        for slot_name, expected_sha in source_shas.items():
            if ctx.read_slot(slot_name).file_sha != expected_sha:
                raise EmaError("stale_revision", "Fișierele lucrării s-au schimbat.", "")
        if needs_import:
            import_piee_into_job(
                ws,
                job,
                data_year,
                sources["anexa"],
                sources.get("questionnaire"),
                sources.get("prelucrare"),
                previous_piee=sources.get("previous_piee"),
            )
        with ws.connect() as db:
            for row in db.execute("SELECT id,revision FROM fields WHERE job_id=?", (job,)):
                ctx.record_read("fields", str(row["id"]), int(row["revision"]))
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
                        "source": "previous_piee" if "previous_piee" in sources else "base",
                    },
                }
            ),
            encoding="utf-8",
        )
        workbook = ctx.artifact_dir() / "Prelucrare-date.xlsx"
        write_prelucrare(data.dataset, data.dataset.years, workbook, data.factors)
        ctx.save_output(workbook, "Prelucrare-date.xlsx")
        ctx.save_output(temporary, "PIEE-draft.docx")
        ctx.progress(2, 2, "Prelucrare date generată")
        return StageOutcome(warnings=[f"untouched anchors: {len(result.untouched)}"])

    return run_stage(ws, job, "piee_generate", stage, on_revision=on_revision)


def set_prelucrare(ws: Workspace, job: str, file_id: str, role: str = "input") -> dict[str, object]:
    if role != "input":
        raise EmaError("file_type", "Tipul fișierului este invalid.", "")
    record = get_job(ws, job)
    if record["type"] != "piee":
        raise EmaError("wrong_job_type", "Lucrarea nu este PIEE.", "")
    if record["state"] == "running":
        raise EmaError("job_running", "Lucrarea rulează deja.", "")
    path = ws.file_path(str(record["client_slug"]), file_id)
    if path.suffix.lower() not in {".xls", ".xlsx"}:
        raise EmaError("file_type", "Tipul fișierului este invalid.", "")
    import_prelucrare(path)
    ws.set_slot(job, "prelucrare", file_id)
    return prelucrare_state(ws, job)
