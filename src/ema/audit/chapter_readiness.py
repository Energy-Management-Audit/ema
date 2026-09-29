"""Refuse a final whose retained chapter would contain only its title."""

from collections.abc import Sequence

from ema.audit.catalogue import CATALOGUE
from ema.core.review.models import Issue
from ema.core.review.section_transition import SectionState, Status


def empty_chapters(states: Sequence[SectionState]) -> list[Issue]:
    by_id = {state.section_id: state for state in states}
    issues: list[Issue] = []
    for chapter in (section for section in CATALOGUE if section.parent is None):
        children = [
            section
            for section in CATALOGUE
            if section.chapter == chapter.chapter and section.parent
        ]
        # Fixed chapters survive N/A drops, while wholly excluded optional chapters disappear.
        if (
            chapter.kind != "fixed"
            and by_id[chapter.id].status == Status.NA
            and all(by_id[section.id].status == Status.NA for section in children)
        ):
            continue
        # A retained introduction counts as content; a bare chapter title does not.
        content = (
            children
            if chapter.kind != "narrative" and children and not chapter.has_intro_content
            else [chapter, *children]
        )
        if not any(by_id[section.id].status == Status.DONE for section in content):
            issues.append(
                Issue(code="chapter_empty", message=f"{chapter.title}: capitolul nu are conținut")
            )
    return issues
