"""Place chapter-four chart groups beside their corresponding source-backed tables."""

from __future__ import annotations

from ema.audit.chapter_four_charts import ChartGroup
from ema.audit.chapter_four_comments import ANNUAL_OPENING, FACTOR_TAIL, TABLE_OPENING
from ema.core.office.blocks import Block, Caption, Paragraph


def _label_at(block: Block, label: str | None) -> bool:
    return isinstance(block, Paragraph) and block.segments == [label]


def _opens(block: Block, opening: str) -> bool:
    return (
        isinstance(block, Paragraph)
        and bool(block.segments)
        and isinstance(block.segments[0], str)
        and block.segments[0].startswith(opening)
    )


def _total_at(block: Block) -> bool:
    return _opens(block, "Total anual")


def _factors_at(block: Block) -> bool:
    return (
        _opens(block, "Curba de")
        and isinstance(block, Paragraph)
        and isinstance(block.segments[-1], str)
        and block.segments[-1].endswith(FACTOR_TAIL)
    )


def _annual_slot(
    group: ChartGroup, body: list[Block], start: int, following: int
) -> tuple[bool, int]:
    """Where a group's annual figures go, as (before the block, its index): share pies after the
    variable factors, a chart before the annual list or else after the table totals."""
    span = range(start, following)
    factors = next((i for i in span if _factors_at(body[i])), None)
    if group.pies and factors is not None:
        return False, factors + 1
    listed = next((i for i in span if _opens(body[i], ANNUAL_OPENING)), None)
    if listed is not None:
        return True, listed
    total = [i for i in span if _total_at(body[i])]
    return False, total[-1] if total else following - 1


def place_chart_groups(blocks: list[Block], groups: dict[str, list[ChartGroup]]) -> list[Block]:
    """Insert monthly charts before the first table and its lead-in, annual charts before the
    annual list, or after the table totals of a section without one; share pies after the
    variable factors."""
    result: list[Block] = []
    index = 0
    while index < len(blocks):
        heading = blocks[index]
        if not isinstance(heading, Paragraph) or not heading.proto.startswith("heading:ch4."):
            result.append(heading)
            index += 1
            continue
        section = heading.proto.removeprefix("heading:")
        end = index + 1
        while end < len(blocks) and not (
            isinstance(blocks[end], Paragraph) and blocks[end].proto.startswith("heading:ch4.")
        ):
            end += 1
        body = blocks[index + 1 : end]
        before: dict[int, list[Block]] = {}
        after: dict[int, list[Block]] = {}
        for group in groups.get(section, []):
            start = (
                next(
                    (i for i, block in enumerate(body) if _label_at(block, group.label)),
                    0,
                )
                if group.label
                else 0
            )
            following = next(
                (
                    i
                    for i in range(start + 1, len(body))
                    if any(
                        other.label is not None
                        and other.label != group.label
                        and _label_at(body[i], other.label)
                        for other in groups.get(section, [])
                    )
                ),
                len(body),
            )
            if group.monthly:
                first_table = next(
                    (
                        i
                        for i in range(start, following)
                        if isinstance(body[i], Caption) or _opens(body[i], TABLE_OPENING)
                    ),
                    following,
                )
                before.setdefault(first_table, []).extend(group.monthly)
            if group.annual:
                ahead, at = _annual_slot(group, body, start, following)
                (before if ahead else after).setdefault(at, []).extend(group.annual)
        result.append(heading)
        for i, block in enumerate(body):
            result.extend(before.get(i, []))
            result.append(block)
            result.extend(after.get(i, []))
        result.extend(before.get(len(body), []))
        if not body:
            result.extend(after.get(-1, []))
        index = end
    return result
