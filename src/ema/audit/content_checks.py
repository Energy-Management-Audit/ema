"""Content gaps that block a final audit deliverable."""

from __future__ import annotations

import sqlite3

from ema.audit.ai_wording import ai_wording
from ema.audit.carrier_gap import blocked_message
from ema.audit.chapter_five_notes import NOTE_PREFIX
from ema.audit.chapter_four_sentences import sentence_plan
from ema.audit.render_dataset import reviewed_dataset
from ema.audit.visit import slug
from ema.core.review.models import Field, Issue
from ema.core.review.section_transition import SectionState, Status
from ema.energy_data.calc import tep
from ema.energy_data.carriers import Carrier, counts_in_total
from ema.energy_data.factors import AUDIT_FACTORS_2026, FactorTable
from ema.energy_data.model import CarrierSeries, EnergyDataset, Reading


def _fields_dataset(fields: dict[str, Field]) -> EnergyDataset | None:
    readings: dict[Carrier, dict[int, CarrierSeries]] = {}
    for key, field in fields.items():
        parts = key.split(".")
        if (
            len(parts) not in {3, 4}
            or parts[0] != "carrier"
            or parts[1] not in Carrier._value2member_map_
            or not parts[2].isdigit()
            or field.unit is None
            or field.value_type != "number"
        ):
            continue
        carrier, year = Carrier(parts[1]), int(parts[2])
        years = readings.setdefault(carrier, {})
        series = years.setdefault(year, CarrierSeries())
        reading = Reading(float(field.value) if field.value is not None else None, field.unit)
        if len(parts) == 3:
            years[year] = CarrierSeries(series.months, reading)
        elif parts[3].isdigit() and 1 <= int(parts[3]) <= 12:
            series.months[int(parts[3])] = reading
    if not readings:
        return None
    years = tuple(sorted({year for series in readings.values() for year in series}))
    return reviewed_dataset(EnergyDataset(years, readings), fields.values())


def _has_arithmetic_conclusion(fields: dict[str, Field]) -> bool:
    dataset = _fields_dataset(fields)
    if dataset is None:
        return False
    try:
        return bool(sentence_plan(dataset, AUDIT_FACTORS_2026).sections.get("ch4.concluzii"))
    except ValueError:
        return False


def total_blockers(dataset: EnergyDataset, factors: FactorTable) -> list[tuple[Carrier, int]]:
    return [
        (carrier, year)
        for year in dataset.years
        for carrier in sorted(dataset.carriers)
        if counts_in_total(carrier)
        and year in dataset.carriers[carrier]
        and tep(dataset, factors, carrier, year).value is None
    ]


def content_issues(db: sqlite3.Connection, job: str) -> list[Issue]:
    fields = {
        str(row["key"]): Field.model_validate_json(row["data"])
        for row in db.execute("SELECT key,data FROM fields WHERE job_id=?", (job,))
    }
    not_applicable = {
        str(row["section_id"])
        for row in db.execute("SELECT section_id,data FROM section_states WHERE job_id=?", (job,))
        if SectionState.parse(row["data"]).status == Status.NA
    }
    count_field = fields.get("audit_measure.count")
    measure_count = (
        int(count_field.value) if count_field and count_field.value is not None else None
    )
    issues: list[Issue] = []
    dataset = _fields_dataset(fields)
    blockers = total_blockers(dataset, AUDIT_FACTORS_2026) if dataset is not None else []
    series_by_carrier = dataset.carriers if dataset is not None else {}
    for carrier, year in blockers:
        key = f"carrier.{carrier.value}.{year}"
        annual = fields.get(key)
        field_id = (
            annual.id
            if annual is not None
            else next(
                (
                    field.id
                    for field_key, field in sorted(fields.items())
                    if field_key.startswith(f"{key}.") and field_key[len(key) + 1 :].isdigit()
                ),
                None,
            )
        )
        issues.append(
            Issue(
                code="data_total_blocked",
                field_id=field_id,
                message=blocked_message(
                    db, job, fields, series_by_carrier[carrier][year], carrier, year
                ),
            )
        )
    active_slots = [
        (str(row["name"]), str(row["file_sha"]))
        for row in db.execute(
            "SELECT s.name, v.file_sha FROM slots s JOIN slot_versions v ON v.job_id=s.job_id "
            "AND v.slot=s.name AND v.version=s.active_version "
            "WHERE s.job_id=? AND (s.name LIKE 'visit/meter/%' OR s.name LIKE 'visit/thermal/%')",
            (job,),
        )
    ]
    active_photos = {sha[:8] for _, sha in active_slots}
    active_panels = {
        slug(parts[2])
        for name, _ in active_slots
        if (parts := name.split("/"))[:2] == ["visit", "meter"] and len(parts) == 4
    }
    for key, field in sorted(fields.items()):
        parts = key.split(".")
        photo_id = (
            parts[2]
            if len(parts) >= 4 and parts[0] == "meter"
            else parts[1]
            if len(parts) >= 3 and parts[0] == "thermal"
            else None
        )
        device_panel = (
            parts[1] if len(parts) == 3 and parts[0] == "meter" and parts[2] == "device" else None
        )
        if field.needs_confirmation and (
            photo_id in active_photos or device_panel in active_panels
        ):
            issues.append(
                Issue(
                    code="reading_unconfirmed",
                    field_id=field.id,
                    message=f"Confirmaţi valoarea de pe fotografie: {field.label}",
                )
            )
        if not key.startswith("narrative.") or key.removeprefix("narrative.") in not_applicable:
            continue
        if key.startswith("narrative.ch6.measure.") and measure_count is not None:
            suffix = key.removeprefix("narrative.ch6.measure.")
            if suffix.isdecimal() and int(suffix) > measure_count:
                continue
        if (
            isinstance(field.value, str)
            and field.review != "rejected"
            and (wording := ai_wording(field.value))
        ):
            issues.append(
                Issue(
                    code="ai_wording",
                    field_id=field.id,
                    message=f"Textul menţionează AI („{wording}”): {field.label}",
                )
            )
        if (field.value is None or field.review == "rejected") and not (
            # An equipment note is optional: a rejected one is simply not printed.
            key.startswith(NOTE_PREFIX)
            or (
                key == "narrative.ch4.concluzii"
                and (blockers or _has_arithmetic_conclusion(fields))
            )
        ):
            issues.append(
                Issue(
                    code="narrative_missing",
                    field_id=field.id,
                    message=f"Textul lipseşte: {field.label}",
                )
            )
    return issues
