"""Persist filed carrier gaps and surface them during PIEE review."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ema.core.review import mark_absent
from ema.core.review.models import Field, FieldSpec, Issue
from ema.core.workspace import Workspace
from ema.energy_data.carriers import CARRIER_NAMES_RO, Carrier

if TYPE_CHECKING:
    from ema.piee.dataset import PieeData


def record_completeness(ws: Workspace, job: str, data: PieeData) -> None:
    for yearly in data.annual_check.years:
        for carrier in yearly.missing_carriers:
            filed = (
                data.prelucrare.filed.get(f"tep.{carrier.value}.{yearly.year}")
                if data.prelucrare is not None
                else None
            ) or data.anexa.annual.get(f"{carrier.value}_raw")
            mark_absent(
                ws,
                job,
                FieldSpec(
                    key=f"carrier.{carrier.value}.{yearly.year}",
                    label=CARRIER_NAMES_RO[carrier],
                    value_type="number",
                    unit=filed.unit if filed is not None else "tep",
                    required=True,
                ),
                "not_found",
            )
        for carrier in yearly.unfiled_carriers:
            mark_absent(
                ws,
                job,
                FieldSpec(
                    key=f"carrier_unfiled.{carrier.value}.{yearly.year}",
                    label=CARRIER_NAMES_RO[carrier],
                    value_type="text",
                ),
                "not_found",
            )


def completeness_issues(job_fields: list[Field]) -> tuple[list[Issue], list[Issue]]:
    blocking: list[Issue] = []
    warnings: list[Issue] = []
    for field in job_fields:
        parts = field.key.split(".")
        if len(parts) != 3 or not parts[2].isdigit():
            continue
        if parts[1] not in Carrier._value2member_map_:
            continue
        carrier = Carrier(parts[1])
        if (
            parts[0] == "carrier"
            and field.required
            and field.presence == "not_found"
            and field.review != "accepted"
        ):
            blocking.append(
                Issue(
                    code="carrier_incomplete",
                    field_id=field.id,
                    message=f"Lipseşte consumul de {CARRIER_NAMES_RO[carrier]} pentru {parts[2]}.",
                )
            )
        elif parts[0] == "carrier_unfiled" and field.presence == "not_found":
            warnings.append(
                Issue(
                    code="carrier_unfiled",
                    field_id=field.id,
                    message=(
                        f"Consumul de {CARRIER_NAMES_RO[carrier]} din {parts[2]} "
                        "nu apare în totalul depus."
                    ),
                )
            )
    return blocking, warnings
