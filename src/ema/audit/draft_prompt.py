"""The chapter call's instructions and requests, in Romanian, in the auditor's register (C3)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from ema.audit.catalogue import CATALOGUE
from ema.audit.catalogue_types import fact_key
from ema.audit.draft_checks import DraftReview, sentence_parts
from ema.audit.draft_plan import Group, SectionPlan, usable
from ema.audit.draft_render import rendered_value
from ema.audit.draft_schema import SECTION_FACTS, SectionDraft
from ema.core.resources import resource_path
from ema.core.review.models import Field

PROMPT_VERSION = "audit-draft-v6"
SUPPORT_VERSION = PROMPT_VERSION + "-support"
# The prompt's numbered rule each check enforces: a retry quotes it beside the error.
RULES = {
    "literal_name": 1,
    "literal_number": 2,
    "fact_refs": 5,
    "fact_missing": 6,
    "ai_mention": 7,
    "passage_verbatim": 8,
    "passage_reused": 9,
    "unit_missing": 14,
    "unit_passage": 14,
    "unit_outside": 14,
    "missing_status_invalid": 15,
    "status_invalid": 16,
    "missing_item_invalid": 18,
}
OMITTED_RULE = (
    "Fiecare secțiune cerută apare o singură dată în sections, cu id-ul ei exact, într-un "
    "răspuns JSON complet după schemă."
)
_TITLES = {section.id: section.title for section in CATALOGUE}


@cache
def instructions() -> str:
    return resource_path("audit", "prompts", "draft_v6.txt").read_text(encoding="utf-8").strip()


def rule_text(code: str) -> str:
    number = RULES.get(code)
    line = next(
        (line for line in instructions().splitlines() if line.startswith(f"{number}. ")), None
    )
    return line.partition(" ")[2] if line is not None else OMITTED_RULE


@dataclass
class Used:
    """What the chapter's accepted sections hold, so that no later call repeats it."""

    passages: set[str] = field(default_factory=set[str])
    openings: dict[str, str] = field(default_factory=dict[str, str])

    def add(self, draft: SectionDraft, passages: set[str], facts: Mapping[str, Field]) -> None:
        self.passages |= passages
        first = next((item for item in draft.paragraphs if item.kind != "missing"), None)
        if first is not None and (parts := sentence_parts(first.text, dict(facts))):
            self.openings[draft.section] = parts[0]

    def payload(self) -> dict[str, Any]:
        return {"used_passages": sorted(self.passages), "opening_sentences": self.openings}


def _missing(plan: SectionPlan) -> list[str]:
    """The section's keys without a usable value, a fact never recorded included: a reference
    part that needs one keeps its place as a missing item (#163 D2)."""
    recorded = {fact_key(key) for key in plan.facts}
    return sorted(
        {key for key, value in plan.facts.items() if not usable(value)}
        | (SECTION_FACTS.get(plan.section, frozenset()) - recorded)
    )


def _section(plan: SectionPlan) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "section": plan.section,
        "title": _TITLES[plan.section],
        "target_words": plan.target,
        "reference": [{"kind": part.kind, "text": part.text} for part in plan.example],
        "facts": [
            {"key": key, "text": rendered_value(value), "unit": value.unit}
            for key, value in sorted(plan.facts.items())
            if usable(value)
        ],
        "missing": _missing(plan),
    }
    if plan.section == "ch3.process":
        entry["units"] = [{"unit": number, "passages": list(keys)} for number, keys in plan.units]
    return entry


def chapter_request(
    group: Group, used: Used, sections: Sequence[str] | None = None
) -> dict[str, Any]:
    plans = [plan for plan in group.sections if sections is None or plan.section in sections]
    return {
        "chapter": group.chapter,
        "sections": [_section(plan) for plan in plans],
        **used.payload(),
    }


def retry_request(
    group: Group,
    used: Used,
    rejected: Mapping[str, SectionDraft],
    errors: Mapping[str, Sequence[DraftReview]],
) -> dict[str, Any]:
    """The failing and omitted sections again, with what the accepted ones already hold."""
    return {
        "request": chapter_request(group, used, list(errors)),
        "rejected_drafts": [rejected[name].model_dump() for name in errors if name in rejected],
        "errors": [
            {
                "section": section,
                "rule": issue.code,
                "rule_text": rule_text(issue.code),
                "location": issue.location,
                "detail": issue.detail,
            }
            for section, issues in errors.items()
            for issue in issues
        ],
    }
