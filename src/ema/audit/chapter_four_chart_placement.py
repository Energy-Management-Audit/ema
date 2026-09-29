"""Place chapter-four chart groups beside their corresponding source-backed tables."""

from __future__ import annotations

from ema.audit.chapter_four_charts import ChartGroup
from ema.core.office.blocks import Block, Caption, Paragraph


def _label_at(block: Block, label: str | None) -> bool:
    return isinstance(block, Paragraph) and block.segments == [label]


def _total_at(block: Block) -> bool:
    return (
        isinstance(block, Paragraph)
        and bool(block.segments)
        and isinstance(block.segments[0], str)
        and block.segments[0].startswith("Total anual")
    )


def place_chart_groups(blocks: list[Block], groups: dict[str, list[ChartGroup]]) -> list[Block]:
    """Insert monthly charts by the first table and annual charts after their table totals."""
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
                    (i for i in range(start, following) if isinstance(body[i], Caption)), following
                )
                before.setdefault(first_table, []).extend(group.monthly)
            if group.annual:
                total = [i for i in range(start, following) if _total_at(body[i])]
                after.setdefault(total[-1] if total else following - 1, []).extend(group.annual)
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
