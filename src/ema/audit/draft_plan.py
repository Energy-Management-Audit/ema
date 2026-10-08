"""What one chapter call drafts: each section's facts, length target and style example (D2, D8;
#143 D5).

A chapter whose targets exceed one call's output allowance splits, in catalogue order, into
consecutive groups under it. The process passages split by unit (D3): ch3.process gets those of
the 3.1.x units, ch3.flux the overview. When no passage has a unit, ch3.process gets them all as
one pool (#155 D1).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ema.audit.catalogue_types import AuditFact, fact_key
from ema.audit.draft_style import Example, ExamplePart
from ema.core.review.models import Field

THINKING_TOKENS = 16_000
MAX_OUTPUT_TOKENS = 65_536
TOKENS_PER_WORD = 1.3
OUTPUT_FACTOR = 2.5
# A section the base gives no own text to measure counts as a short one in the allowance.
UNMEASURED_WORDS = 150


@dataclass(frozen=True)
class SectionPlan:
    section: str
    facts: dict[str, Field]
    target: int | None
    # The reference audit's section, redacted, in its order (#163 D2).
    example: tuple[ExamplePart, ...]
    # ch3.process only: every 3.1.x unit, from 1, with the passage keys that are its own.
    units: tuple[tuple[int, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class Group:
    id: str
    chapter: int
    sections: tuple[SectionPlan, ...]
    # The reference audit's identity, recorded in each draft's fingerprint (#163).
    reference: str = ""

    @property
    def allowance(self) -> int:
        return allowance(plan.target for plan in self.sections)


def allowance(targets: Iterable[int | None]) -> int:
    """A chapter call's output tokens: thinking, then the drafts at about 2.5 tokens per token
    of prose, which carries fact tokens and the JSON around it."""
    words = sum(UNMEASURED_WORDS if target is None else target for target in targets)
    return min(MAX_OUTPUT_TOKENS, THINKING_TOKENS + int(OUTPUT_FACTOR * words * TOKENS_PER_WORD))


def usable(field: Field) -> bool:
    return field.presence == "found" and field.review != "rejected" and bool(field.evidence)


def _process_passage(key: str) -> bool:
    return fact_key(key) == AuditFact.PROCESS_SECTIONS


def pooled(facts: Mapping[str, Field], units: Mapping[str, int | None]) -> bool:
    """No process passage has a unit: they come from the permit and the description rather
    than the flow schemes, so the overview would starve ch3.process of every one (#155 D1)."""
    passages = [key for key in facts if _process_passage(key)]
    return bool(passages) and all(units.get(key) is None for key in passages)


def offered(
    section: str, facts: Mapping[str, Field], units: Mapping[str, int | None]
) -> dict[str, Field]:
    """The section's facts, with each process passage given to its unit or to the overview;
    pooled, every passage goes to ch3.process."""
    if section not in {"ch3.flux", "ch3.process"}:
        return dict(facts)
    overview = section == "ch3.flux"
    if pooled(facts, units):
        return {
            key: field for key, field in facts.items() if not (overview and _process_passage(key))
        }
    return {
        key: field
        for key, field in facts.items()
        if not _process_passage(key) or (units.get(key) is None) == overview
    }


def plan_section(
    section: str,
    facts: Mapping[str, Field],
    example: Example | None,
    units: Mapping[str, int | None],
    unit_count: int = 1,
) -> SectionPlan:
    """The section's facts and target: her base section's own words once it has a usable fact,
    general text making up the length the facts leave (#143 D5); none without one.

    A 3.1.x unit is a copy of the base's unit text, so ch3.process aims at that length for each
    unit that has passages; pooled, at two units' length in unit 1, since her audits describe at
    least two production sections.
    """
    own = offered(section, facts, units)
    pool = section == "ch3.process" and pooled(facts, units)
    grouped: tuple[tuple[int, tuple[str, ...]], ...] = ()
    described = 0
    if pool:
        keys = sorted(key for key, field in own.items() if _process_passage(key) and usable(field))
        grouped = ((1, tuple(keys)),)
        described = 2 * bool(keys)
    elif section == "ch3.process":
        grouped = tuple(
            (
                number,
                tuple(
                    sorted(
                        key
                        for key, field in own.items()
                        if _process_passage(key) and units.get(key) == number and usable(field)
                    )
                ),
            )
            for number in range(1, unit_count + 1)
        )
        described = sum(bool(keys) for _, keys in grouped)
    if example is None or not example.words:
        target = None
    elif section == "ch3.process":
        target = example.words * described or None
    else:
        target = example.words if any(usable(field) for field in own.values()) else None
    return SectionPlan(section, own, target, example.parts if example else (), grouped)


def split(chapter: int, plans: Iterable[SectionPlan]) -> list[Group]:
    """Consecutive groups in catalogue order, each under the output bound; a section that
    exceeds it alone is a group of its own, at the bound."""
    batches: list[list[SectionPlan]] = []
    for plan in plans:
        current = batches[-1] if batches else None
        if current and allowance(item.target for item in (*current, plan)) < MAX_OUTPUT_TOKENS:
            current.append(plan)
        else:
            batches.append([plan])
    return [
        Group(f"{chapter}-{index}", chapter, tuple(batch)) for index, batch in enumerate(batches, 1)
    ]
