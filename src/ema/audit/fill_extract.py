"""Fill v2: one structured extraction pass over the dossier, each fact verified by Ema."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ema.audit.catalogue import Section
from ema.audit.catalogue_labels import field_label
from ema.audit.catalogue_types import MAX_PASSAGES, PASSAGE_FACTS, passage_key
from ema.audit.fill_files import file_ids, resolve_name
from ema.audit.fill_tools import FillDocument, FillTools
from ema.core.errors import EmaError
from ema.core.llm import AgentContext, RecordingProvider, ReplayProvider, complete_json
from ema.core.llm.types import Provider
from ema.core.logging import write_event
from ema.core.resources import resource_path
from ema.core.review.fields import fields
from ema.core.workspace import Workspace

PROMPT_VERSION = "audit-extract-v1"
PROMPT_TOKENS = 300_000
OUTPUT_TOKENS = 8_000
CHARS_PER_TOKEN = 4
PASSAGE_CHARS = 3_000
PASSAGE_TOKENS = PASSAGE_CHARS // CHARS_PER_TOKEN
PASSAGE_MARK = "pasaj"


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
    lines = (
        f"{key} — {field_label(key)} — {section}"
        + (f" — {PASSAGE_MARK}" if key in PASSAGE_FACTS else "")
        for key, section in facts
    )
    return "Fapte de stabilit:\n" + "\n".join(lines)


def output_tokens(facts: Sequence[tuple[str, str]]) -> int:
    """The output allowance: the short facts, plus every passage a narrative fact may take."""
    passages = len({key for key, _ in facts if key in PASSAGE_FACTS}) * MAX_PASSAGES
    return OUTPUT_TOKENS + passages * PASSAGE_TOKENS


def file_text(file_id: str, document: FillDocument) -> str:
    pages = (f"[{file_id} p.{number}]\n{text}" for number, text in enumerate(document.pages, 1))
    return f"{file_id}: {document.name}\n" + "\n".join(pages)


def file_groups(head: str, files: Sequence[str]) -> list[list[str]]:
    """Files in dossier order, grouped so each call's prompt stays under PROMPT_TOKENS."""
    bound = PROMPT_TOKENS * CHARS_PER_TOKEN
    groups: list[list[str]] = [[]]
    size = len(head)
    for text in files:
        if len(head) + len(text) + 2 <= bound:
            pieces = [text]
        else:
            header, *pages = text.split("\n[")
            pieces = [header + "\n[" + page for page in pages] if pages else [text]
        for piece in pieces:
            if len(head) + len(piece) + 2 > bound:
                raise EmaError("ai_prompt_size", "Pagina depăşeşte limita AI.", str(len(piece)))
            separator = 2 if groups[-1] else 0
            if size + len(piece) + separator > bound:
                groups.append([])
                size = len(head)
                separator = 0
            groups[-1].append(piece)
            size += len(piece) + separator
    assert all(len(head + "\n\n".join(group)) <= bound for group in groups)
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

    def __call__(self, content: str, output_limit: int) -> Extraction:
        self.calls += 1
        prompt = instructions()

        def estimate_tokens(messages: list[dict[str, object]]) -> int:
            tokens = prompt_tokens("".join(str(message["content"]) for message in messages))
            if tokens > PROMPT_TOKENS:
                raise EmaError("ai_prompt_size", "Cererea depăşeşte limita AI.", str(tokens))
            return tokens

        def log_estimate(tokens: int, estimate: float, spent: float) -> None:
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
                context,
                Extraction,
                prompt,
                content,
                max_output_tokens=output_limit,
                estimate_tokens=estimate_tokens,
                on_estimate=log_estimate,
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
    rejected: Sequence[tuple[ExtractedFact, EmaError]],
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
        for fact, error in rejected
    ]
    wanted = [(key, section) for key, section in facts if key in {fact.key for fact, _ in rejected}]
    return (
        facts_text(wanted)
        + "\n\nFapte respinse:\n"
        + json.dumps(items, ensure_ascii=False, indent=1)
    )


def _target(
    fact: ExtractedFact, kept: Sequence[str], verified: set[str]
) -> tuple[str, str | int | float] | None:
    """The key and value to record, or None: a narrative fact's next passage is its quote."""
    if fact.key not in PASSAGE_FACTS:
        return None if fact.key in verified else (fact.key, fact.value)
    if fact.quote in kept or len(kept) == MAX_PASSAGES:
        return None
    return passage_key(fact.key, len(kept) + 1), fact.quote


def _drop_stale_passages(
    tools: Mapping[str, FillTools],
    owner: Mapping[str, str],
    passages: Mapping[str, Sequence[str]],
    found: set[str],
) -> None:
    """Passages beyond this run's count are a previous dossier's and must not reach a draft."""
    for key in sorted(PASSAGE_FACTS & owner.keys()):
        for number in range(max(2, len(passages.get(key, ())) + 1), MAX_PASSAGES + 1):
            if passage_key(key, number) in found:
                tools[owner[key]].mark_missing({"key": passage_key(key, number)})


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
    passages: dict[str, list[str]] = {}
    rejected: list[tuple[ExtractedFact, EmaError]] = []

    def verify(extraction: Extraction) -> None:
        # The first verified fact per key wins; an unrequested key is ignored. A narrative
        # fact keeps each distinct passage, up to MAX_PASSAGES, and its value is the passage.
        for fact in extraction.facts:
            kept = passages.get(fact.key, [])
            target = _target(fact, kept, verified) if fact.key in owner else None
            if target is None:
                continue
            key, value = target
            try:
                tools[owner[fact.key]].record_fact(
                    {
                        "key": key,
                        "value": value,
                        "name": fact.file,
                        "page": fact.page,
                        "quote": fact.quote,
                    }
                )
            except EmaError as exc:
                rejected.append((fact, exc))
                continue
            passages[fact.key] = [*kept, fact.quote]
            verified.add(fact.key)

    head = facts_text(facts) + "\n\nFişiere:\n"
    ids = file_ids(documents)
    files = [file_text(file_id, documents[name]) for file_id, name in ids.items()]
    if facts and files:
        for group in file_groups(instructions() + head, files):
            verify(call(head + "\n\n".join(group), output_tokens(facts)))
    # A rejected passage is retried even when another passage of its fact was verified.
    retry = [
        (fact, error)
        for fact, error in rejected
        if fact.key not in verified or fact.key in PASSAGE_FACTS
    ]
    first_pass = {fact.key: error.code for fact, error in retry}
    if retry:
        wanted = [(key, section) for key, section in facts if key in first_pass]
        verify(call(retry_text(facts, retry, documents), output_tokens(wanted)))
    # A value found earlier, as from the Necesar info, is never overwritten with missing.
    found = {item.key for item in fields(ws, job) if item.presence == "found"}
    missing = tuple(key for key in owner if key not in verified and key not in found)
    for key in missing:
        tools[owner[key]].mark_missing({"key": key})
    _drop_stale_passages(tools, owner, passages, found)
    return ExtractSummary(
        call.calls, tuple(key for key in owner if key in verified), first_pass, missing
    )
