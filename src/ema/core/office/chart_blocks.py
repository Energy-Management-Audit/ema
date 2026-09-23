"""Detached native chart blocks for insertion at an arbitrary document location."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
from pathlib import Path

from lxml import etree

from ema.core.office.chart_series import Series
from ema.core.office.charts import _column_root, _new_chart, _set_series
from ema.core.office.package import read_parts, write_parts, xml


def clone_chart_detached(
    docx: Path,
    part: str,
    series: list[Series],
    title: str | None,
    out: Path,
    prototype_paragraph: etree._Element,
) -> tuple[str, etree._Element]:
    """Clone a native chart and return its drawing paragraph for caller placement."""
    parts = read_parts(docx)
    root = copy.deepcopy(xml(parts, part))
    _set_series(root, series, title)
    new_part, paragraph = _new_chart(
        parts, part, part, root, detached=True, prototype_paragraph=prototype_paragraph
    )
    write_parts(parts, out)
    return new_part, paragraph


def build_column_chart_detached(
    docx: Path,
    style_source_part: str,
    series: list[Series],
    axis_title: str,
    out: Path,
    prototype_paragraph: etree._Element,
) -> tuple[str, etree._Element]:
    """Build a column chart using S0's style and return its drawing paragraph."""
    parts = read_parts(docx)
    root = _column_root(parts, style_source_part, series, axis_title)
    new_part, paragraph = _new_chart(
        parts,
        style_source_part,
        style_source_part,
        root,
        detached=True,
        prototype_paragraph=prototype_paragraph,
    )
    write_parts(parts, out)
    return new_part, paragraph
