"""The support pass: one verdict per drafted sentence, fail-closed (D4).

A client sentence is supported by the facts it cites; a general one unless it states or implies
something about the client, or is technically wrong. A sentence without a verdict is
unsupported. When the pass cannot run, or answers a sentence twice, no section of the group is
accepted: each fails as support_unavailable and is drafted again on the next run.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from itertools import takewhile
from typing import Any, Literal

from pydantic import BaseModel
from pydantic import Field as ModelField

from ema.audit.draft_checks import (
    ANY_TOKEN,
    DraftReview,
    sentence_parts,
    texts,
    token_only,
)
from ema.audit.draft_render import kept
from ema.audit.draft_schema import SectionDraft
from ema.core.errors import EmaError
from ema.core.llm.agent import AgentContext
from ema.core.llm.structured import complete_json
from ema.core.review.models import Field

SUPPORT_PROMPT = (
    "Each item is a sentence of an energy audit, with the values of the facts it cites. Return "
    'one verdict per item, with its location, sentence_index and kind. kind is "client" when '
    "the sentence says something about this client (its company, sites, activity, equipment, "
    'suppliers, consumption or history), and "general" when it explains a process, an '
    "equipment type, a utility, standard practice or the regulatory context, or introduces or "
    "links ideas. A client sentence is supported only when the cited facts state everything it "
    "claims, including any qualitative claim; a quantity, a cause or an assessment the facts do "
    "not state is unsupported. A general sentence is supported unless it states or implies a "
    "fact about this client, such as a named supplier, site, equipment or practice of the "
    "client, or is technically wrong. Do not infer missing facts. Keep each reason under "
    "fifteen words."
)
# Per sentence: a verdict of at most 120 tokens (kind and reason), after the model's thinking
# (D2). A call asks for at most 32,000 tokens of verdicts; a larger group is asked in batches.
THINKING_TOKENS = 16_000
VERDICT_TOKENS = 120
MAX_VERDICT_TOKENS = 32_000
MAX_OUTPUT_TOKENS = 65_536
INTRO_WITHOUT_ITEMS = "list introduction without supported items"


class Verdict(BaseModel):
    location: str
    sentence_index: int
    kind: Literal["client", "general"]
    supported: bool
    reason: str = ""


class SupportVerdicts(BaseModel):
    verdicts: list[Verdict] = ModelField(default_factory=list[Verdict])


def _sentences(
    drafts: Sequence[SectionDraft], facts: dict[str, Field]
) -> list[tuple[str, str, int, str]]:
    """(section, location, index, sentence) for every sentence that claims something itself."""
    return [
        (draft.section, location, index, sentence)
        for draft in drafts
        for location, item in texts(draft)
        for index, sentence in enumerate(sentence_parts(item.text, facts))
        if not token_only(sentence)
    ]


def support_allowance(sentences: int) -> int:
    return min(MAX_OUTPUT_TOKENS, THINKING_TOKENS + VERDICT_TOKENS * sentences)


def support_request(drafts: Sequence[SectionDraft], facts: dict[str, Field]) -> list[Any]:
    return [
        {
            "location": f"{section}:{location}",
            "sentence_index": index,
            "sentence": sentence,
            "facts": {
                key: str(facts[key].value) for key in ANY_TOKEN.findall(sentence) if key in facts
            },
        }
        for section, location, index, sentence in _sentences(drafts, facts)
    ]


def support_pass(
    context: AgentContext, drafts: Sequence[SectionDraft], facts: dict[str, Field]
) -> dict[str, tuple[DraftReview, ...]]:
    """Per section, its unsupported sentences, which the render drops, with any list
    introduction left without items; a pass that cannot run raises support_unavailable."""
    sentences = _sentences(drafts, facts)
    flags: dict[str, list[DraftReview]] = {draft.section: [] for draft in drafts}
    if not sentences:
        return {section: () for section in flags}
    request = support_request(drafts, facts)
    size = MAX_VERDICT_TOKENS // VERDICT_TOKENS
    verdicts: dict[tuple[str, int], Verdict] = {}
    try:
        for start in range(0, len(request), size):
            batch = request[start : start + size]
            result = complete_json(
                context,
                SupportVerdicts,
                SUPPORT_PROMPT,
                json.dumps(batch, ensure_ascii=False),
                max_output_tokens=support_allowance(len(batch)),
                schema_retries=0,
                thinking_tokens=THINKING_TOKENS,
            )
            for verdict in result.verdicts:
                key = (verdict.location, verdict.sentence_index)
                if key in verdicts:
                    # Two verdicts leave the sentence undecided: the answer is off the schema.
                    raise EmaError(
                        "ai_schema",
                        "Răspunsul AI nu respectă formatul cerut.",
                        f"duplicate verdict {verdict.location}#{verdict.sentence_index}",
                    )
                verdicts[key] = verdict
    except EmaError as exc:
        raise EmaError(
            "support_unavailable",
            "Verificarea redactării nu a rulat; secţiunea se reface la următoarea redactare.",
            exc.code,
        ) from exc
    for section, location, index, sentence in sentences:
        given = verdicts.get((f"{section}:{location}", index))
        if given is None or not given.supported:
            reason = given.reason if given is not None else "no verdict"
            flags[section].append(DraftReview("unsupported", location, reason, sentence))
    for draft in drafts:
        flags[draft.section].extend(orphan_intros(draft, tuple(flags[draft.section]), facts))
    return {section: tuple(items) for section, items in flags.items()}


def orphan_intros(
    draft: SectionDraft, flags: tuple[DraftReview, ...], facts: dict[str, Field]
) -> list[DraftReview]:
    """A list introduction whose items were all dropped goes with them, and the review says so."""
    found: list[DraftReview] = []
    for index, item in enumerate(draft.paragraphs):
        following = draft.paragraphs[index + 1 :]
        bullets = list(takewhile(lambda paragraph: paragraph.kind == "bullet", following))
        if item.kind != "body" or not bullets:
            continue
        if any(
            kept(bullet, f"paragraph:{index + offset}", flags, facts)
            for offset, bullet in enumerate(bullets, 1)
        ):
            continue
        sentences = kept(item, f"paragraph:{index}", flags, facts)
        if sentences and sentences[-1].rstrip().endswith(":"):
            found.append(
                DraftReview("unsupported", f"paragraph:{index}", INTRO_WITHOUT_ITEMS, sentences[-1])
            )
    return found
