"""Chapter five's 'Importanța echipamentului' notes: one call per measurements run, checked.

Each panel and each thermal item with a component gets one short paragraph on what the equipment
does and why it matters. A note is optional: with AI off, a failed call or a failed check, the
item has none and the chapter prints nothing in its place.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from ema.audit.ai_wording import ai_wording
from ema.audit.catalogue_types import AuditFact, fact_key
from ema.audit.draft_checks import (
    ACRONYM,
    NAME,
    NAME_COMMON,
    NUMBER_WORD,
    SENTENCE_WORD,
    UPPER,
    folded,
    sentence_parts,
    traced,
)
from ema.audit.draft_plan import MAX_OUTPUT_TOKENS, THINKING_TOKENS, usable
from ema.audit.fill_stage import settings_provider
from ema.audit.research_quote import in_quote
from ema.core.config import load_settings
from ema.core.errors import EmaError
from ema.core.jobs import StageContext
from ema.core.llm import AgentContext, RecordingProvider, ReplayProvider, complete_json
from ema.core.llm.types import Provider
from ema.core.logging import write_event
from ema.core.resources import resource_path
from ema.core.review import propose
from ema.core.review.models import Evidence, Field, FieldSpec, Manual

if TYPE_CHECKING:
    from ema.audit.chapter_five import ChapterFivePlan

NOTE_PREFIX = "narrative.ch5.equipment."
NOTE_LABEL = "Importanța echipamentului: "
PROMPT_VERSION = "audit-ch5-equipment-v1"
MAX_SENTENCES = 2
MAX_WORDS = 45
# A note is a sentence or two; its JSON, at about this many tokens, follows the thinking.
TOKENS_PER_NOTE = 250
ACTIVITY_FACTS = frozenset({AuditFact.BUSINESS_ACTIVITY, AuditFact.CAEN_DESCRIPTION})
DIGITS = re.compile(r"\d+")
# A sentence's opening capitalised word, as "Compresorul" or "ABB".
OPENING = re.compile(rf"^[{UPPER}][\w-]*")


class EquipmentNote(BaseModel):
    id: str
    text: str


class EquipmentNotes(BaseModel):
    notes: list[EquipmentNote]


@dataclass(frozen=True)
class NoteItem:
    id: str
    name: str
    # The item's own texts: a panel's label and device, a thermal item's component.
    texts: tuple[str, ...]

    def request(self) -> dict[str, str]:
        if self.id.startswith("thermal:"):
            return {"id": self.id, "component": self.name}
        return {"id": self.id, "label": self.name} | (
            {"device": self.texts[1]} if len(self.texts) > 1 else {}
        )


def note_key(item_id: str) -> str:
    return NOTE_PREFIX + item_id


@cache
def instructions() -> str:
    path = resource_path("audit", "prompts", "ch5_equipment_v1.txt")
    return path.read_text(encoding="utf-8").strip()


def note_items(plan: ChapterFivePlan, facts: Mapping[str, Field]) -> list[NoteItem]:
    """The panels and component-named thermal items that have no note field yet: a rerun never
    proposes over a note, which would make it a conflict."""
    items = [
        NoteItem(panel.id, panel.label, (panel.label, *([panel.device] if panel.device else [])))
        for panel in plan.panels
    ]
    items.extend(
        NoteItem(f"thermal:{photo.sha[:8]}", photo.component, (photo.component,))
        for photo in plan.thermal
        if photo.component
    )
    return [item for item in items if note_key(item.id) not in facts]


def activity(facts: Mapping[str, Field]) -> list[str]:
    return [
        str(field.value)
        for key, field in sorted(facts.items())
        if fact_key(key) in ACTIVITY_FACTS and usable(field)
    ]


def _openings(text: str) -> list[str]:
    """Opening words that look like a name: all caps or with a digit. An ordinary capitalised
    word, as "Compresorul", only starts a sentence; the words after it are name candidates
    already, so "Atlas Copco" still fails on "Copco"."""
    found: list[str] = []
    for sentence in sentence_parts(text, {}):
        match = OPENING.match(sentence)
        if match is None:
            continue
        first = match.group()
        if any(char.isdigit() for char in first) or (len(first) >= 2 and first.isupper()):
            found.append(first)
    return found


def note_issues(text: str, own: Sequence[str], client: Sequence[str]) -> list[str]:
    """Why a note cannot stand: AI wording, its length, or a number or name no fact shows."""
    issues: list[str] = []
    if ai_wording(text):
        issues.append("ai_wording")
    if len(sentence_parts(text, {})) > MAX_SENTENCES or len(text.split()) > MAX_WORDS:
        issues.append("length")
    source = " ".join(own)
    if set(DIGITS.findall(text)) - set(DIGITS.findall(source)) or set(
        NUMBER_WORD.findall(folded(text))
    ) - set(NUMBER_WORD.findall(folded(source))):
        issues.append("literal_number")
    # A capital that opens the note starts a sentence, not a name.
    marked = ". " + text if SENTENCE_WORD.match(text) else text
    common = {name.casefold() for name in NAME_COMMON}
    known = [traced(value) for value in (*own, *client)]
    if any(
        name.casefold() not in common and not any(in_quote(traced(name), value) for value in known)
        for name in (*NAME.findall(marked), *ACRONYM.findall(text), *_openings(text))
    ):
        issues.append("literal_name")
    return issues


def _source(ctx: StageContext, recording: Path | None) -> tuple[Provider, str] | None:
    """The recording replayed, else the live provider recorded beside the run; none with the
    client-documents switch off, the one Draft uses."""
    if recording is not None:
        replay = ReplayProvider(recording)
        return replay, replay.model_id
    settings = load_settings(ctx.ws)
    if not settings.ai_client_live:
        return None
    provider, model_id = settings_provider(settings)
    return RecordingProvider(provider, ctx.artifact_dir() / "ch5-equipment.json"), model_id


def _log(ctx: StageContext, event: str, **values: object) -> None:
    with ctx.ws.connect() as db, ctx.ws.job_log(db, ctx.job) as handle:
        write_event(handle, event, run=ctx.run_id, **values)


def _evidence(job: str, item: NoteItem, text: str, model_id: str) -> Evidence:
    return Evidence(
        id=hashlib.sha256(f"{job}:ch5-equipment:{item.id}:{text}".encode()).hexdigest(),
        provenance="manual",
        locator=Manual(who="agent", note=f"{PROMPT_VERSION} {model_id}"),
        method="manual",
        retrieved_at=datetime.now(UTC),
        highlight="none",
    )


def write_notes(
    ctx: StageContext,
    plan: ChapterFivePlan,
    facts: Mapping[str, Field],
    recording: Path | None,
) -> tuple[list[Field], list[str]]:
    """Ask once for every item without a note, propose each note that passes its checks; the
    proposed fields and the stage warnings."""
    items = note_items(plan, facts)
    if not items:
        return [], []
    client = activity(facts)
    try:
        source = _source(ctx, recording)
        if source is None:
            return [], []
        provider, model_id = source
        ctx.record_input(prompt=PROMPT_VERSION, model=model_id)
        context = AgentContext(
            ctx.ws,
            ctx.job,
            "ch5:equipment",
            provider,
            model_id,
            PROMPT_VERSION,
            client_live=provider.name != "replay",
        )
        request = {"items": [item.request() for item in items]} | (
            {"activity": client} if client else {}
        )
        answer = complete_json(
            context,
            EquipmentNotes,
            instructions(),
            json.dumps(request, ensure_ascii=False),
            max_output_tokens=min(
                MAX_OUTPUT_TOKENS, THINKING_TOKENS + TOKENS_PER_NOTE * len(items)
            ),
            schema_retries=0,
            thinking_tokens=THINKING_TOKENS,
        )
    except (EmaError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, EmaError) else type(exc).__name__
        _log(ctx, "ch5_notes_failed", code=code, detail=str(exc))
        return [], [f"ch5.equipment: {code}"]
    by_id = {item.id: item for item in items}
    seen: set[str] = set()
    texts: dict[str, str] = {}
    dropped: list[dict[str, str]] = []
    for note in answer.notes:
        text = note.text.strip().removeprefix(NOTE_LABEL.strip()).strip()
        if note.id not in by_id:
            reason = "unknown"
        elif note.id in seen:
            reason = "duplicate"
        elif not text:
            # A blank note would leave a field that renders nothing and is never asked again.
            reason = "blank"
        else:
            reason = ", ".join(note_issues(text, by_id[note.id].texts, client))
        seen.add(note.id)
        if reason:
            dropped.append({"id": note.id, "reason": reason})
        else:
            texts[note.id] = text
    if dropped:
        _log(ctx, "ch5_notes_dropped", notes=dropped)
    proposed = [
        propose(
            ctx.ws,
            ctx.job,
            FieldSpec(
                key=note_key(item_id),
                label=f"Importanța echipamentului – {by_id[item_id].name}",
                value_type="text",
                chapter="ch5",
            ),
            text,
            [_evidence(ctx.job, by_id[item_id], text, model_id)],
            state="enriched",
        )
        for item_id, text in texts.items()
    ]
    return proposed, []
