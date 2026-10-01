"""Automatic layout and readable axes for generated native charts."""

# pyright: reportPrivateUsage=false

from lxml import etree

from ema.core.office.chart_series import Series
from ema.core.office.package import C

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def automatic_layout(root: etree._Element, series: list[Series]) -> None:
    for layout in root.findall(f".//{{{C}}}plotArea/{{{C}}}layout/{{{C}}}manualLayout") + [
        layout
        for axis in ("catAx", "valAx", "dateAx", "serAx")
        for layout in root.findall(
            f".//{{{C}}}plotArea/{{{C}}}{axis}/{{{C}}}title/{{{C}}}layout/{{{C}}}manualLayout"
        )
    ]:
        parent = layout.getparent()
        assert parent is not None
        parent.remove(layout)
    if any(point is None for item in series for point in item.values):
        for trendline in root.iter(f"{{{C}}}trendline"):
            parent = trendline.getparent()
            assert parent is not None
            parent.remove(trendline)


def _child(owner: etree._Element, tag: str, before: tuple[str, ...] = ()) -> etree._Element:
    item = owner.find(tag)
    if item is None:
        item = etree.Element(tag)
        following = next((node for node in owner if node.tag in before), None)
        if following is None:
            owner.append(item)
        else:
            following.addprevious(item)
    return item


def _monthly_axis(axis: etree._Element) -> None:
    _child(axis, f"{{{C}}}tickLblSkip", (f"{{{C}}}tickMarkSkip", f"{{{C}}}noMultiLvlLbl")).set(
        "val", "1"
    )
    text = _child(axis, f"{{{C}}}txPr", (f"{{{C}}}crossAx",))
    _child(text, A + "bodyPr", (A + "lstStyle", A + "p")).set("rot", "-2700000")
    _child(text, A + "lstStyle", (A + "p",))
    paragraph = _child(text, A + "p")
    properties = _child(paragraph, A + "pPr", (A + "r", A + "endParaRPr"))
    font = _child(properties, A + "defRPr")
    font.set("sz", "1000")
    for tag in ("latin", "ea", "cs"):
        _child(font, A + tag).set("typeface", "Times New Roman")


def column_axes(root: etree._Element, series: list[Series]) -> None:
    # audit-01's monthly category labels are Times New Roman 10 pt, rotated 45 degrees.
    if series and all(len(item.categories) == 12 for item in series):
        for axis in root.findall(f".//{{{C}}}catAx"):
            _monthly_axis(axis)
    maximum = max(
        (point for item in series for point in item.values if point is not None), default=0
    )
    for axis in root.findall(f".//{{{C}}}valAx"):
        number = _child(
            axis,
            f"{{{C}}}numFmt",
            tuple(
                f"{{{C}}}" + tag
                for tag in (
                    "majorTickMark",
                    "minorTickMark",
                    "tickLblPos",
                    "spPr",
                    "txPr",
                    "crossAx",
                )
            ),
        )
        number.set("formatCode", "#,##0.00" if maximum < 10 else "#,##0")
        number.set("sourceLinked", "0")


def value_axis(axis: etree._Element) -> None:
    """Keep zero as the minimum and let Word choose the remaining scale."""
    for tag in ("majorUnit", "minorUnit"):
        node = axis.find(f"{{{C}}}{tag}")
        if node is not None:
            axis.remove(node)
    scaling = axis.find(f"{{{C}}}scaling")
    if scaling is None:
        scaling = etree.Element(f"{{{C}}}scaling")
        axis.insert(1, scaling)
    maximum = scaling.find(f"{{{C}}}max")
    if maximum is not None:
        scaling.remove(maximum)
    minimum = scaling.find(f"{{{C}}}min")
    if minimum is None:
        minimum = etree.SubElement(scaling, f"{{{C}}}min")
    minimum.set("val", "0")
    title = axis.find(f"{{{C}}}title")
    if title is not None:
        fixed = title.find(f"{{{C}}}layout")
        if fixed is not None:
            title.remove(fixed)
