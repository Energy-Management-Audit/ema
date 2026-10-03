"""The Fill stage: one agent run per applicable chapter 2-3 section records its facts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ema.audit.catalogue import CATALOGUE, Section
from ema.audit.catalogue_labels import field_label
from ema.audit.dossier import dossier_documents
from ema.audit.draft_schema import SECTION_FACTS
from ema.audit.fill_files import file_ids
from ema.audit.fill_tools import FillDocument, FillTools
from ema.audit.sections import record_applicability
from ema.core.config import Settings, load_settings
from ema.core.errors import EmaError
from ema.core.jobs import StageContext, StageOutcome, run_stage, status, subscribe
from ema.core.llm import (
    AgentContext,
    GeminiProvider,
    Limits,
    OpenAIProvider,
    RecordingProvider,
    ReplayProvider,
    default_model,
    run_agent,
    selected_model,
)
from ema.core.llm.agent import AgentState, job_spend
from ema.core.llm.types import Provider
from ema.core.logging import write_event
from ema.core.resources import resource_path
from ema.core.review.section_transition import Status
from ema.core.workspace import Workspace

PROMPT_VERSION = "audit-fill-v1"
FILL_STEPS = 12
# Codes after which no further section can succeed in this run.
STOPPING = {
    "ai_quota_day": "Cota zilnică a furnizorului AI s-a epuizat",
    "ai_budget": "Bugetul AI al lucrării s-a epuizat",
}


@dataclass(frozen=True)
class FillSummary:
    run: str
    sections: dict[str, str] = field(default_factory=dict[str, str])
    failed: dict[str, str] = field(default_factory=dict[str, str])
    not_applicable: tuple[str, ...] = ()
    stopped: tuple[str, ...] = ()


def instructions() -> str:
    return resource_path("audit", "prompts", "fill_v1.txt").read_text(encoding="utf-8").strip()


def fill_task(section: Section, documents: Sequence[str]) -> str:
    facts = "\n".join(f"{fact} — {field_label(str(fact))}" for fact in section.facts)
    return (
        f"Secţiunea {section.id} „{section.title}”. Fapte de stabilit:\n{facts}\n"
        "Fişiere:\n" + "\n".join(f"{key}: {name}" for key, name in file_ids(documents).items())
    )


def settings_provider(settings: Settings) -> tuple[Provider, str]:
    name = settings.provider
    if name not in {"gemini", "openai"}:
        raise EmaError("provider_invalid", "Furnizorul este invalid.", str(name))
    model = settings.model or default_model(name).id
    selected_model(name, model)
    provider_class = GeminiProvider if name == "gemini" else OpenAIProvider
    provider = provider_class(
        settings.provider_key(name), settings.llm_live, client_live=settings.ai_client_live
    )
    return provider, model


def fill_section(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    section: Section,
    documents: dict[str, FillDocument],
    *,
    provider: Provider,
    model_id: str,
    limits: Limits,
    client_live: bool = False,
) -> AgentState:
    tools = FillTools(ws, job, section.id, documents)
    context = AgentContext(
        ws, job, section.id, provider, model_id, PROMPT_VERSION, client_live=client_live
    )
    task = fill_task(section, list(documents))
    return run_agent(context, instructions(), tools.tools(), limits, task=task)


def _failure_code(exc: EmaError) -> str:
    # The agent wraps provider refusals as ai_provider; the cause names what happened.
    cause = exc.__cause__
    return cause.code if exc.code == "ai_provider" and isinstance(cause, EmaError) else exc.code


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
            code = failed[name] = _failure_code(exc)
            with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
                write_event(handle, "fill_failed", run=ctx.run_id, file=name, code=code)
    wanted = [item for item in CATALOGUE if item.id in SECTION_FACTS]
    if sections is not None:
        wanted = [item for item in wanted if item.id in sections]
    done: dict[str, str] = {}
    not_applicable: list[str] = []
    for index, section in enumerate(wanted):
        try:
            state = record_applicability(ctx.ws, ctx.job, section.id)
            if state.applicability is False or state.status == Status.NA:
                not_applicable.append(section.id)
                continue
            recorded = (
                provider
                if isinstance(provider, ReplayProvider)
                else RecordingProvider(provider, ctx.artifact_dir() / f"{section.id}.json")
            )
            agent = fill_section(
                ctx.ws,
                ctx.job,
                section,
                documents,
                provider=recorded,
                model_id=model_id,
                limits=Limits(FILL_STEPS),
                client_live=settings.ai_client_live,
            )
        except EmaError as exc:
            code = failed[section.id] = _failure_code(exc)
            with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
                write_event(handle, "fill_failed", run=ctx.run_id, section=section.id, code=code)
            if code in STOPPING:
                return FillSummary(
                    ctx.run_id,
                    done,
                    failed,
                    tuple(not_applicable),
                    tuple(item.id for item in wanted[index + 1 :]),
                )
            continue
        done[section.id] = agent.status
    return FillSummary(ctx.run_id, done, failed, tuple(not_applicable))


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
        item_failures=[f"{section}: {code}" for section, code in summary.failed.items()],
        warnings=stopped_warning(summary.failed, summary.stopped),
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
