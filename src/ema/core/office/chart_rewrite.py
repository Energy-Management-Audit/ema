"""Rewrite an authored Word bar chart in place through its hidden bookmark."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from lxml import etree

from ema.core.office.anchor_targets import chart_target
from ema.core.office.anchors import find
from ema.core.office.chart_layout import value_axis
from ema.core.office.chart_series import Series, _ref, _series
from ema.core.office.charts import _embed, _set_series, _write_cache
from ema.core.office.package import C, encoded, rels_path, xml

CT = "http://schemas.openxmlformats.org/package/2006/content-types"


def _axes(root: etree._Element) -> None:
    plot = root.find(f"{{{C}}}chart/{{{C}}}plotArea")
    if plot is None:
        raise ValueError("authored chart has no plot area")
    layout = plot.find(f"{{{C}}}layout")
    if layout is not None:
        plot.remove(layout)
    for axis in plot.findall(f"{{{C}}}valAx"):
        value_axis(axis)


def rewrite_bar_chart(
    parts: dict[str, bytes],
    slot: str,
    series: tuple[Series | None, ...],
    title: str | None = None,
    *,
    cache_name_override: str | None = None,
) -> str:
    """Update caches and embed one workbook without locating a chart by position or text."""
    target = chart_target(parts, slot)
    if target.part is None:
        raise ValueError("chart bookmark has no chart part")
    root = xml(parts, target.part)
    bars = list(root.iter(f"{{{C}}}barChart"))
    if len(bars) != 1:
        raise ValueError("chart bookmark does not target one bar chart")
    authored = bars[0].findall(f"{{{C}}}ser")
    names = [item.name for item in _series(root)]
    if len(authored) != len(series):
        raise ValueError("chart plan series count differs from authored prototype")
    retained: list[Series] = []
    for index, (node, item) in enumerate(zip(authored, series, strict=True)):
        if item is None:
            bars[0].remove(node)
        else:
            retained.append(Series(item.name or names[index], item.categories, item.values))
    if not retained:
        raise ValueError("chart cannot have no series")
    _set_series(root, retained, title)
    _axes(root)
    _embed(parts, target.part, root)
    if cache_name_override is not None:
        for node in root.iter(f"{{{C}}}ser"):
            name_ref = _ref(node, "tx")
            if name_ref is None:
                raise ValueError("chart series has no name reference")
            _write_cache(name_ref, [cache_name_override])
        parts[target.part] = encoded(root)
    return target.part


def remove_chart(parts: dict[str, bytes], slot: str) -> str:
    """Remove a missing figure drawing, relationship, chart part and content type."""
    target = chart_target(parts, slot)
    if target.part is None:
        raise ValueError("chart bookmark has no chart part")
    owner = xml(parts, target.owner)
    paragraph = find([owner], slot)
    parent = paragraph.getparent()
    if parent is None:
        raise ValueError("chart paragraph has no parent")
    parent.remove(paragraph)
    parts[target.owner] = encoded(owner)
    path = rels_path(target.owner)
    relations = xml(parts, path)
    relation = next((item for item in relations if item.get("Id") == target.relationship_id), None)
    if relation is None:
        raise ValueError("chart relationship is missing")
    relations.remove(relation)
    parts[path] = encoded(relations)
    parts.pop(target.part)
    parts.pop(rels_path(target.part), None)
    types = xml(parts, "[Content_Types].xml")
    for item in list(types):
        if item.tag == f"{{{CT}}}Override" and item.get("PartName") == "/" + target.part:
            types.remove(item)
    parts["[Content_Types].xml"] = encoded(types)
    return target.part
