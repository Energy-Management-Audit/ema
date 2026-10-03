"""The Fill stage: one extraction pass over the dossier for every applicable section."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from ema.audit.catalogue import CATALOGUE, Section
from ema.audit.dossier import dossier_documents
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.fill_extract import PROMPT_VERSION, ExtractSummary, extract_facts
from ema.audit.fill_tools import FillDocument
from ema.audit.sections import record_applicability
from ema.core.config import Settings, load_settings
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, run_stage, status, subscribe
from ema.core.llm import GeminiProvider, OpenAIProvider, default_model, selected_model
from ema.core.llm.agent import job_spend
from ema.core.llm.types import Provider
from ema.core.logging import write_event
from ema.core.review.section_transition import Status
from ema.core.workspace import Workspace

# Codes after which no further section can succeed in this run.
STOPPING = {
    "ai_quota_day": "Cota zilnică a furnizorului AI s-a epuizat",
    "ai_budget": "Bugetul AI al lucrării s-a epuizat",
    "ai_credits": "Creditul furnizorului AI s-a epuizat",
}


@dataclass(frozen=True)
class FillSummary:
    run: str
    sections: dict[str, str] = field(default_factory=dict[str, str])
    failed: dict[str, str] = field(default_factory=dict[str, str])
    not_applicable: tuple[str, ...] = ()
    extracted: ExtractSummary | None = None


def settings_provider(settings: Settings) -> tuple[Provider, str]:
    name = settings.provider
    if name not in {"gemini", "openai"}:
        raise EmaError("provider_invalid", "Furnizorul este invalid.", str(name))
    model = settings.model or default_model(name).id
    selected_model(name, model)
    if name == "gemini":
        provider = GeminiProvider(
            settings.provider_key(name),
            settings.llm_live,
            client_live=settings.ai_client_live,
            transport_retries=False,
        )
    else:
        provider = OpenAIProvider(
            settings.provider_key(name), settings.llm_live, client_live=settings.ai_client_live
        )
    return provider, model


def _failure_code(exc: EmaError) -> str:
    # Provider refusals are wrapped as ai_provider; the cause names what happened.
    cause = exc.__cause__
    return cause.code if exc.code == "ai_provider" and isinstance(cause, EmaError) else exc.code


def _provider_failure(exc: EmaError) -> dict[str, str | int]:
    cause = exc.__cause__
    provider_error = cause.__cause__ if isinstance(cause, EmaError) else cause
    fields: dict[str, str | int] = {}
    if provider_error is not None:
        code = getattr(provider_error, "code", None)
        status = getattr(provider_error, "status_code", None)
        if isinstance(code, str):
            fields["provider_code"] = code
        if isinstance(status, int):
            fields["provider_status"] = status
    return fields


def _log_failure(
    ctx: StageContext, code: str, exc: EmaError | None = None, **where: object
) -> None:
    with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
        write_event(
            handle,
            "fill_failed",
            run=ctx.run_id,
            **where,
            code=code,
            **(_provider_failure(exc) if exc is not None else {}),
        )


def _file_id(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def _fill(ctx: StageContext, sections: Sequence[str] | None) -> FillSummary:
    settings = load_settings(ctx.ws)
    provider, model_id = settings_provider(settings)
    ctx.record_input(prompt=PROMPT_VERSION, model=model_id)
    slots = {
        version.slot.removeprefix("dossier/"): version.slot for version in ctx.read_slots("dossier")
    }
    documents: dict[str, FillDocument] = {}
    failed: dict[str, str] = {}
    for name, slot in slots.items():
        try:
            documents.update(dossier_documents(ctx.ws, ctx.job, {name: slot}))
        except EmaError as exc:
            failed[name] = _failure_code(exc)
            _log_failure(ctx, failed[name], file_sha=_file_id(name))
    wanted = [item for item in CATALOGUE if item.id in SECTION_FACTS]
    if sections is not None:
        wanted = [item for item in wanted if item.id in sections]
    applicable: list[Section] = []
    not_applicable: list[str] = []
    for section in wanted:
        try:
            state = record_applicability(ctx.ws, ctx.job, section.id)
        except EmaError as exc:
            failed[section.id] = _failure_code(exc)
            _log_failure(ctx, failed[section.id], exc, section=section.id)
            continue
        if state.applicability is False or state.status == Status.NA:
            not_applicable.append(section.id)
        else:
            applicable.append(section)
    try:
        extracted = extract_facts(
            ctx.ws,
            ctx.job,
            applicable,
            documents=documents,
            provider=provider,
            model_id=model_id,
            artifacts=ctx.artifact_dir(),
            client_live=settings.ai_client_live,
        )
    except EmaError as exc:
        code = _failure_code(exc)
        failed.update((section.id, code) for section in applicable)
        _log_failure(ctx, code, exc, sections=[section.id for section in applicable])
        return FillSummary(ctx.run_id, {}, failed, tuple(not_applicable))
    done = {section.id: "done" for section in applicable}
    return FillSummary(ctx.run_id, done, failed, tuple(not_applicable), extracted)


def stopped_warning(failed: dict[str, str], stopped: Sequence[str]) -> list[str]:
    """The warning for sections a quota or the job budget left undone."""
    if not stopped:
        return []
    cause = next(STOPPING[code] for code in reversed(failed.values()) if code in STOPPING)
    return [f"{cause}: {len(stopped)} secţiuni rămase."]


def log_spend(ctx: StageContext, stage: str, before: float) -> None:
    """One job log line with what the stage's AI calls cost."""
    total = job_spend(ctx.ws, ctx.job)
    with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
        write_event(
            handle,
            "ai_spend",
            run=ctx.run_id,
            stage=stage,
            usd=round(total - before, 6),
            job_usd=round(total, 6),
        )


def _outcome(summary: FillSummary) -> StageOutcome:
    return StageOutcome(
        item_failures=[
            f"{section if section in SECTION_FACTS else _file_id(section)}: {code}"
            for section, code in summary.failed.items()
        ]
    )


def start_fill(
    ws: Workspace,
    job: str,
    sections: Sequence[str] | None = None,
    *,
    on_revision: int | None = None,
    summaries: list[FillSummary] | None = None,
) -> str:
    unknown = sorted(set(sections or ()) - set(SECTION_FACTS))
    if unknown:
        raise EmaError("section_missing", "Secţiunea lipseşte.", ", ".join(unknown))

    def stage(ctx: StageContext) -> StageOutcome:
        before = job_spend(ctx.ws, ctx.job)
        try:
            summary = _fill(ctx, sections)
        finally:
            log_spend(ctx, "fill", before)
        if summaries is not None:
            summaries.append(summary)
        return _outcome(summary)

    return run_stage(ws, job, "fill", stage, on_revision=on_revision)


def fill_sections(ws: Workspace, job: str, sections: Sequence[str] | None = None) -> FillSummary:
    """Run the Fill stage and wait for it, as the CLI's `audit run <job> fill` does."""
    summaries: list[FillSummary] = []
    run = start_fill(ws, job, sections, summaries=summaries)
    for _ in subscribe(ws, job):
        pass
    recorded = next(item for item in status(ws, job).runs if item["id"] == run)
    if recorded["state"] != "ready" or not summaries:
        raise EmaError("fill_failed", "Completarea secţiunilor a eşuat.", str(recorded["error"]))
    return summaries[0]
