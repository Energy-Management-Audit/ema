"""PIEE job generation shared by the command line and future HTTP adapter."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, run_stage
from ema.core.workspace import Workspace
from ema.energy_data.prelucrare_writer import write_prelucrare
from ema.piee.base import build_local_base
from ema.piee.compose import compose_draft, load_approved_base
from ema.piee.dataset import load
from ema.piee.intake import import_piee


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
    base = base_directory(ws)
    job = import_piee(
        ws,
        request.client,
        request.year,
        request.anexa,
        request.necesar,
        request.prelucrare,
        previous_piee=request.previous_piee,
    )
    today = generated_on or date.today()

    def stage(ctx: StageContext) -> StageOutcome:
        anexa_source = ws.file_path(request.client, ctx.read_slot("anexa").file_sha)
        necesar_source = (
            ws.file_path(request.client, ctx.read_slot("questionnaire").file_sha)
            if request.necesar is not None
            else None
        )
        prelucrare_source = (
            ws.file_path(request.client, ctx.read_slot("prelucrare").file_sha)
            if request.prelucrare is not None
            else None
        )
        previous_source = (
            ws.file_path(request.client, ctx.read_slot("previous_piee").file_sha)
            if request.previous_piee is not None
            else None
        )
        data = load(request.year, anexa_source, necesar_source, prelucrare_source, previous_source)
        ctx.record_input(template=load_approved_base(base).base_sha, factors=data.factors.version)
        temporary = ctx.artifact_dir() / "PIEE-draft.docx"
        result = compose_draft(data, base, temporary, today)
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
                        "source": "previous_piee" if request.previous_piee else "base",
                    },
                }
            ),
            encoding="utf-8",
        )
        workbook = ctx.artifact_dir() / "Prelucrare-date.xlsx"
        write_prelucrare(data.dataset, data.dataset.years, workbook, data.factors)
        ctx.save_output(workbook, "Prelucrare-date.xlsx")
        ctx.save_output(temporary, "PIEE-draft.docx")
        return StageOutcome(warnings=[f"untouched anchors: {len(result.untouched)}"])

    return job.id, run_stage(ws, job.id, "piee_generate", stage)
