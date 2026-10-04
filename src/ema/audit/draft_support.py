"""The support pass: one verdict per drafted sentence, fail-closed (D1).

A sentence without a verdict is unsupported. When the pass cannot run, or answers a sentence
twice, every sentence that carries a citation is unsupported; one whose facts are all rendered
keeps its text.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel
from pydantic import Field as ModelField

from ema.audit.draft_checks import (
    ANY_TOKEN,
    CITE,
    DraftReview,
    sentence_parts,
    texts,
    token_only,
)
from ema.audit.draft_schema import SectionDraft
from ema.core.errors import EmaError
from ema.core.llm.agent import AgentContext
from ema.core.llm.structured import complete_json
from ema.core.review.models import Field

SUPPORT_PROMPT = (
    "Each item is a sentence of an energy audit, with the values of the facts it cites. Return "
    "one verdict per item, with its location and sentence_index: supported is true only when the "
    "cited facts state everything the sentence claims, including any qualitative claim. A claim "
    "beyond them, a quantity, a cause or an assessment the facts do not state, is unsupported. "
    "Do not infer missing facts. Keep each reason under fifteen words."
)
# Per sentence: a verdict of at most 40 tokens, after the model's thinking (D2).
THINKING_TOKENS = 16_000
VERDICT_TOKENS = 40
MAX_OUTPUT_TOKENS = 65_536


class Verdict(BaseModel):
    location: str
    sentence_index: int
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
    """Per section, its unsupported sentences; a failed pass marks the cited ones instead."""
    sentences = _sentences(drafts, facts)
    flags: dict[str, list[DraftReview]] = {draft.section: [] for draft in drafts}
    if not sentences:
        return {section: () for section in flags}
    try:
        result = complete_json(
            context,
            SupportVerdicts,
            SUPPORT_PROMPT,
            json.dumps(support_request(drafts, facts), ensure_ascii=False),
            max_output_tokens=support_allowance(len(sentences)),
            schema_retries=0,
        )
        verdicts: dict[tuple[str, int], Verdict] = {}
        for verdict in result.verdicts:
            key = (verdict.location, verdict.sentence_index)
            if key in verdicts:
                # Two verdicts leave the sentence undecided: the whole answer is off the schema.
                raise EmaError(
                    "ai_schema",
                    "Răspunsul AI nu respectă formatul cerut.",
                    f"duplicate verdict {verdict.location}#{verdict.sentence_index}",
                )
            verdicts[key] = verdict
    except EmaError as exc:
        for section, location, _, sentence in sentences:
            if CITE.search(sentence):
                flags[section].append(
                    DraftReview("unsupported", location, "support_unavailable", sentence)
                )
        for items in flags.values():
            items.append(DraftReview("support_unavailable", "section", exc.code))
        return {section: tuple(items) for section, items in flags.items()}
    for section, location, index, sentence in sentences:
        given = verdicts.get((f"{section}:{location}", index))
        if given is None or not given.supported:
            reason = given.reason if given is not None else "no verdict"
            flags[section].append(DraftReview("unsupported", location, reason, sentence))
    return {section: tuple(items) for section, items in flags.items()}
