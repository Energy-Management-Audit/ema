"""Rerunnable audit dossier intake and deterministic completeness."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ema.audit.checklist import ChecklistItem, read_checklist
from ema.audit.intake_agent import classify_unplaced
from ema.core.errors import EmaError
from ema.core.intake import ItemOutcome, intake_file
from ema.core.jobs import StageContext, StageOutcome
from ema.core.llm import Limits, ReplayProvider
from ema.core.office.convert import stored_file
from ema.core.office.sniff import FileKind

_PREFIX = re.compile(r"^(0|1[0-3]|[1-9])(?:\.\d+)?\.")


@dataclass(frozen=True)
class IntakeRecord:
    slot: str
    name: str
    kind: str
    status: str
    item: int | None
    evidence: str | None
    error_code: str | None


@dataclass(frozen=True)
class Completeness:
    checklist: tuple[ChecklistItem, ...]
    files: tuple[IntakeRecord, ...]
    received: dict[int, tuple[str, ...]]
    missing: tuple[int, ...]
    visit_material: tuple[str, ...]
    unclassified: tuple[str, ...]


def classify_name(name: str, checklist: tuple[ChecklistItem, ...]) -> int | None:
    match = _PREFIX.match(name)
    if match is None:
        return None
    number = int(match.group(1))
    if number == 0 or number in {item.number for item in checklist}:
        return number
    return None


def _result(
    slot: str, name: str, outcome: ItemOutcome, checklist: tuple[ChecklistItem, ...]
) -> IntakeRecord:
    item = classify_name(name, checklist)
    return IntakeRecord(
        slot,
        name,
        outcome.kind.value,
        outcome.status,
        item,
        name if item is not None else None,
        outcome.error_code,
    )


def build_completeness(
    checklist: tuple[ChecklistItem, ...],
    files: tuple[IntakeRecord, ...],
) -> Completeness:
    received = {
        item.number: tuple(
            file.slot.removeprefix("dossier/") for file in files if file.item == item.number
        )
        for item in checklist
    }
    missing = tuple(number for number, names in received.items() if not names)
    visit = tuple(file.slot for file in files if file.slot.startswith("visit/"))
    unclassified = tuple(
        file.slot.removeprefix("dossier/")
        for file in files
        if file.item is None and not file.slot.startswith("visit/")
    )
    return Completeness(checklist, files, received, missing, visit, unclassified)


def audit_intake(
    ctx: StageContext,
    *,
    collection: str = "dossier",
    replay: ReplayProvider | None = None,
    limits: Limits | None = None,
) -> StageOutcome:
    slots = ctx.read_slots(collection)
    checklist_slots = [version for version in slots if Path(version.slot).name.startswith("0.")]
    if len(checklist_slots) != 1:
        raise EmaError("checklist_file", "Fișierul Necesar info lipsește sau este ambiguu.", "")
    _, checklist_path = stored_file(ctx.ws, ctx.job, checklist_slots[0].file_sha)
    checklist = read_checklist(checklist_path)
    records: list[IntakeRecord] = []
    failures: list[str] = []
    for version in slots:
        if ctx.cancelled():
            break
        name = Path(version.slot).name
        # Conversion changes the active slot version; the run must not stale itself.
        ctx.reads.pop(("slots", f"{ctx.job}:{version.slot}"), None)
        try:
            outcome = intake_file(ctx, version.slot)
        except (EmaError, OSError, ValueError) as exc:
            outcome = ItemOutcome(
                version.slot,
                version.version,
                version.file_sha,
                FileKind.UNKNOWN,
                "failed",
                error_code=exc.code if isinstance(exc, EmaError) else type(exc).__name__,
            )
        record = _result(version.slot, name, outcome, checklist)
        records.append(record)
        if record.status in {"failed", "needs_conversion"}:
            failures.append(f"{record.slot}: {record.error_code or record.status}")
    warnings: list[str] = []
    unplaced = {
        record.slot.removeprefix(f"{collection}/"): record.slot
        for record in records
        if record.item is None
    }
    if unplaced and replay is not None:
        try:
            tools, state = classify_unplaced(ctx, unplaced, checklist, replay, limits or Limits(20))
        except (EmaError, OSError, ValueError) as exc:
            code = exc.code if isinstance(exc, EmaError) else type(exc).__name__
            warnings.append(f"Clasificarea AI așteaptă reluarea: {code}")
        else:
            records = [
                IntakeRecord(
                    record.slot,
                    record.name,
                    record.kind,
                    record.status,
                    tools.classifications.get(
                        record.slot.removeprefix(f"{collection}/"), record.item
                    ),
                    tools.evidence.get(record.slot.removeprefix(f"{collection}/"), record.evidence),
                    record.error_code,
                )
                for record in records
            ]
            if state != "done":
                warnings.append(f"Clasificarea AI poate fi reluată: {state}")
    report = build_completeness(checklist, tuple(records))
    (ctx.artifact_dir() / "completeness.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return StageOutcome(item_failures=failures, warnings=warnings)
