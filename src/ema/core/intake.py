"""Intake legacy file versions from a job collection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome
from ema.core.logging import write_event
from ema.core.office.convert import ConversionFailed, convert_doc, stored_file
from ema.core.office.sniff import FileKind, sniff
from ema.core.workspace.conversion import active_version


@dataclass(frozen=True)
class ItemOutcome:
    slot: str
    version: int
    file_sha: str
    kind: FileKind
    status: str
    original_words: int | None = None
    converted_words: int | None = None
    shape_words: int | None = None
    warning: str | None = None
    error_code: str | None = None
    detail: str | None = None


def intake_file(ctx: StageContext, slot: str) -> ItemOutcome:
    version = active_version(ctx.ws, ctx.job, slot)
    if version is None:
        raise EmaError("slot_missing", "Fişierul cerut lipseşte.", slot)
    _, path = stored_file(ctx.ws, ctx.job, version.file_sha)
    # This stage updates the slot; recording its old revision would mark its own run stale.
    ctx.inputs[f"slot:{slot}"] = version.file_sha
    detected = sniff(path)
    if ctx.cancelled():
        return ItemOutcome(slot, version.version, version.file_sha, detected.kind, "cancelled")
    if version.converted_from is not None:
        return ItemOutcome(
            slot, version.version, version.file_sha, detected.kind, "already_converted"
        )
    if detected.kind == FileKind.DOC:
        try:
            converted = convert_doc(ctx.ws, ctx.job, slot, version, load_settings(ctx.ws))
        except ConversionFailed as exc:
            return ItemOutcome(
                slot,
                version.version,
                version.file_sha,
                detected.kind,
                "needs_conversion" if exc.code == "needs_conversion" else "failed",
                error_code=exc.code,
                detail=exc.detail,
            )
        if converted is None:
            warning = (
                "Fișierul a fost înlocuit în timpul conversiei; rulați din nou preluarea "
                "pentru noua versiune (R21)."
            )
            return ItemOutcome(
                slot,
                version.version,
                version.file_sha,
                detected.kind,
                "superseded",
                warning=warning,
            )
        check = converted.text_check
        return ItemOutcome(
            slot,
            version.version,
            version.file_sha,
            detected.kind,
            "converted",
            original_words=check.original_words,
            converted_words=check.converted_words,
            shape_words=check.shape_words,
            warning=check.warning,
        )
    if detected.kind == FileKind.XLS:
        state = "readable"
    elif (
        detected.kind == FileKind.HTML
        and detected.mismatch
        and path.suffix.casefold() in {".xls", ".xlsx"}
    ):
        state = "html_as_xls"
    else:
        state = "detected"
    return ItemOutcome(
        slot,
        version.version,
        version.file_sha,
        detected.kind,
        state,
        warning=detected.detail if detected.mismatch else None,
    )


def _record_result(ctx: StageContext, result: ItemOutcome) -> None:
    with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
        write_event(
            handle,
            "intake_file",
            run_id=ctx.run_id,
            slot=result.slot,
            version=result.version,
            file_sha=result.file_sha,
            kind=result.kind.value,
            status=result.status,
            original_words=result.original_words,
            converted_words=result.converted_words,
            shape_words=result.shape_words,
            warning=result.warning,
            error_code=result.error_code,
            detail=result.detail,
        )


def _summary(results: list[ItemOutcome]) -> StageOutcome:
    failures = [
        f"{item.slot} v{item.version}: {item.error_code}: {item.detail}"
        for item in results
        if item.status == "failed"
    ]
    warnings = [
        f"{item.slot} v{item.version}: {warning}"
        for item in results
        if (warning := item.warning or (item.detail if item.status == "needs_conversion" else None))
    ]
    return StageOutcome(item_failures=failures, warnings=warnings)


def intake_legacy(
    ctx: StageContext,
    collection: str,
    on_result: Callable[[ItemOutcome], None] | None = None,
) -> StageOutcome:
    results: list[ItemOutcome] = []
    versions = ctx.read_slots(collection)
    for version in versions:
        # Conversion writes this slot; its pre-conversion revision is not a stale read.
        ctx.reads.pop(("slots", f"{ctx.job}:{version.slot}"), None)
        if ctx.cancelled():
            break
        try:
            result = intake_file(ctx, version.slot)
        except (EmaError, OSError, ValueError) as exc:
            result = ItemOutcome(
                version.slot,
                version.version,
                version.file_sha,
                FileKind.UNKNOWN,
                "failed",
                error_code=exc.code if isinstance(exc, EmaError) else type(exc).__name__,
                detail=exc.detail if isinstance(exc, EmaError) else str(exc),
            )
        results.append(result)
        _record_result(ctx, result)
        if on_result is not None:
            on_result(result)
    return _summary(results)


def intake_stage(
    ctx: StageContext, slot: str, on_result: Callable[[ItemOutcome], None] | None = None
) -> StageOutcome:
    result = intake_file(ctx, slot)
    _record_result(ctx, result)
    if on_result is not None:
        on_result(result)
    return _summary([result])
