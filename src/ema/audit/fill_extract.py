"""Fill v2: one structured extraction pass over the dossier, each fact verified by Ema."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ema.audit.catalogue import Section
from ema.audit.catalogue_labels import field_label
from ema.audit.fill_files import file_ids, resolve_name
from ema.audit.fill_tools import FillDocument, FillTools
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.llm import AgentContext, RecordingProvider, ReplayProvider, complete_json
from ema.core.llm.agent import job_spend
from ema.core.llm.models import selected_model
from ema.core.llm.types import Provider
from ema.core.logging import write_event
from ema.core.resources import resource_path
from ema.core.review.fields import fields
from ema.core.workspace import Workspace

PROMPT_VERSION = "audit-extract-v1"
PROMPT_TOKENS = 300_000
OUTPUT_TOKENS = 8_000
CHARS_PER_TOKEN = 4


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str | int | float
    file: str
    page: int
    quote: str


class Extraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[ExtractedFact]
    missing: list[str]


@dataclass(frozen=True)
class ExtractSummary:
    calls: int
    facts: tuple[str, ...] = ()
    rejected: dict[str, str] = field(default_factory=dict[str, str])
    missing: tuple[str, ...] = ()


def instructions() -> str:
    return resource_path("audit", "prompts", "extract_v1.txt").read_text(encoding="utf-8").strip()


def prompt_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def facts_text(facts: Sequence[tuple[str, str]]) -> str:
    """The facts to establish, one `key — Romanian label — section id` line each."""
    lines = (f"{key} — {field_label(key)} — {section}" for key, section in facts)
    return "Fapte de stabilit:\n" + "\n".join(lines)


def file_text(file_id: str, document: FillDocument) -> str:
    pages = (f"[{file_id} p.{number}]\n{text}" for number, text in enumerate(document.pages, 1))
    return f"{file_id}: {document.name}\n" + "\n".join(pages)


def file_groups(head: str, files: Sequence[str]) -> list[list[str]]:
    """Files in dossier order, grouped so each call's prompt stays under PROMPT_TOKENS."""
    bound = PROMPT_TOKENS * CHARS_PER_TOKEN
    groups: list[list[str]] = [[]]
    size = len(head)
    for text in files:
        if groups[-1] and size + len(text) + 2 > bound:
            groups.append([])
            size = len(head)
        groups[-1].append(text)
        size += len(text) + 2
    return groups


@dataclass
class _Caller:
    ws: Workspace
    job: str
    provider: Provider
    model_id: str
    artifacts: Path
    client_live: bool
    calls: int = 0

    def __call__(self, content: str) -> Extraction:
        self.calls += 1
        prompt = instructions()
        provider_name = (
            self.provider.provider_name
            if isinstance(self.provider, ReplayProvider)
            else self.provider.name
        )
        tokens = prompt_tokens(prompt + content)
        estimate = selected_model(provider_name, self.model_id).cost(tokens, OUTPUT_TOKENS)
        spent = job_spend(self.ws, self.job)
        with self.ws.connect() as db, self.ws.job_log(db, self.job) as handle:
            write_event(
                handle,
                "ai_estimate",
                stage="fill",
                call=self.calls,
                tokens=tokens,
                usd=round(estimate, 6),
                job_usd=round(spent, 6),
            )
        if spent + estimate > load_settings(self.ws).ai_job_budget_usd:
            raise EmaError(
                "ai_budget",
                "Bugetul AI al lucrării s-a epuizat.",
                f"{spent:.2f} + {estimate:.2f} USD",
            )
        provider = (
            self.provider
            if isinstance(self.provider, ReplayProvider)
            else RecordingProvider(self.provider, self.artifacts / f"extract-{self.calls}.json")
        )
        context = AgentContext(
            self.ws,
            self.job,
            "extract",
            provider,
            self.model_id,
            PROMPT_VERSION,
            client_live=self.client_live,
        )
        try:
            return complete_json(
                context, Extraction, prompt, content, max_output_tokens=OUTPUT_TOKENS
            )
        except EmaError:
            raise
        except Exception as exc:
            raise EmaError(
                "ai_provider", "AI nu este disponibil; reluaţi etapa.", type(exc).__name__
            ) from exc


def _page_text(documents: Mapping[str, FillDocument], fact: ExtractedFact) -> str:
    name = resolve_name(fact.file, list(documents))
    pages = documents[name].pages if name is not None else ()
    return pages[fact.page - 1] if 1 <= fact.page <= len(pages) else ""


def retry_text(
    facts: Sequence[tuple[str, str]],
    rejected: Mapping[str, tuple[ExtractedFact, EmaError]],
    documents: Mapping[str, FillDocument],
) -> str:
    """Only the rejected items, each with its reason and its cited page; never the dossier."""
    items = [
        {
            **fact.model_dump(),
            "reason": f"{error.code}: {error.user_message_ro}"
            + (f" ({error.detail})" if error.detail else ""),
            "page_text": _page_text(documents, fact),
        }
        for fact, error in rejected.values()
    ]
    wanted = [(key, section) for key, section in facts if key in rejected]
    return (
        facts_text(wanted)
        + "\n\nFapte respinse:\n"
        + json.dumps(items, ensure_ascii=False, indent=1)
    )


def extract_facts(  # noqa: PLR0913
    ws: Workspace,
    job: str,
    sections: Sequence[Section],
    *,
    documents: dict[str, FillDocument],
    provider: Provider,
    model_id: str,
    artifacts: Path,
    client_live: bool = False,
) -> ExtractSummary:
    """Establish every fact of the given sections from the dossier in one pass and one retry."""
    facts = [(str(fact), section.id) for section in sections for fact in section.facts]
    owner: dict[str, str] = {}
    for key, section in facts:
        owner.setdefault(key, section)
    tools = {section.id: FillTools(ws, job, section.id, documents) for section in sections}
    call = _Caller(ws, job, provider, model_id, artifacts, client_live)
    verified: set[str] = set()
    rejected: dict[str, tuple[ExtractedFact, EmaError]] = {}

    def verify(extraction: Extraction) -> None:
        # The first verified fact per key wins; an unrequested key is ignored.
        for fact in extraction.facts:
            if fact.key not in owner or fact.key in verified:
                continue
            try:
                tools[owner[fact.key]].record_fact(
                    {"key": fact.key, "value": fact.value, "name": fact.file, "quote": fact.quote}
                )
            except EmaError as exc:
                rejected.setdefault(fact.key, (fact, exc))
                continue
            verified.add(fact.key)

    head = facts_text(facts) + "\n\nFişiere:\n"
    ids = file_ids(documents)
    files = [file_text(file_id, documents[name]) for file_id, name in ids.items()]
    if facts and files:
        for group in file_groups(instructions() + head, files):
            verify(call(head + "\n\n".join(group)))
    retry = {key: item for key, item in rejected.items() if key not in verified}
    first_pass = {key: error.code for key, (_, error) in retry.items()}
    if retry:
        verify(call(retry_text(facts, retry, documents)))
    # A value found earlier, as from the Necesar info, is never overwritten with missing.
    found = {item.key for item in fields(ws, job) if item.presence == "found"}
    missing = tuple(key for key in owner if key not in verified and key not in found)
    for key in missing:
        tools[owner[key]].mark_missing({"key": key})
    return ExtractSummary(
        call.calls, tuple(key for key in owner if key in verified), first_pass, missing
    )
